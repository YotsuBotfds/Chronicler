//! Exact native checkpoint state.
//!
//! A compact, versioned binary encoding of every field the three simulators
//! carry from one tick to the next, so a resumed run continues from the very
//! state an uninterrupted run holds instead of a state rebuilt from Python.
//!
//! Layout of one state blob (all integers little endian):
//!
//! ```text
//! magic     8 bytes   b"CHRNSTAT"
//! version   u32       STATE_VERSION
//! kind      u8        1 = AgentSimulator, 2 = EcologySimulator, 3 = PoliticsSimulator
//! schema    u64       FNV-1a 64 of the kind's type schema (field names and types)
//! payload   ...       the fields, in declaration order
//! ```
//!
//! Every persisted struct is listed with [`persist_struct!`], which
//! destructures it without `..`: adding a field to a persisted struct fails
//! to compile until the field is persisted (or explicitly skipped as
//! derived state). The schema string, and so the fingerprint, changes with
//! any field name, order or type, so a blob from another layout is refused
//! with a clear error instead of being misread.

use std::collections::HashMap;
use std::hash::Hash;

pub const STATE_MAGIC: &[u8; 8] = b"CHRNSTAT";
pub const STATE_VERSION: u32 = 1;

pub const KIND_AGENT: u8 = 1;
pub const KIND_ECOLOGY: u8 = 2;
pub const KIND_POLITICS: u8 = 3;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PersistError(pub String);

impl PersistError {
    pub fn new(msg: impl Into<String>) -> Self {
        Self(msg.into())
    }
}

impl std::fmt::Display for PersistError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for PersistError {}

pub type Result<T> = std::result::Result<T, PersistError>;

#[derive(Default)]
pub struct Writer {
    pub buf: Vec<u8>,
}

impl Writer {
    pub fn new() -> Self {
        Self { buf: Vec::new() }
    }
}

pub struct Reader<'a> {
    buf: &'a [u8],
    pos: usize,
}

impl<'a> Reader<'a> {
    pub fn new(buf: &'a [u8]) -> Self {
        Self { buf, pos: 0 }
    }

    pub fn take(&mut self, n: usize) -> Result<&'a [u8]> {
        let end = self
            .pos
            .checked_add(n)
            .filter(|&end| end <= self.buf.len())
            .ok_or_else(|| PersistError::new(format!(
                "native state truncated: need {n} bytes at offset {}, have {}",
                self.pos,
                self.buf.len() - self.pos
            )))?;
        let out = &self.buf[self.pos..end];
        self.pos = end;
        Ok(out)
    }

    pub fn remaining(&self) -> usize {
        self.buf.len() - self.pos
    }

    /// A length prefix, bounded by the bytes left so a corrupt length cannot
    /// request an absurd allocation.
    fn len(&mut self, min_item_bytes: usize) -> Result<usize> {
        let n = u64::get(self)?;
        let n = usize::try_from(n).map_err(|_| PersistError::new("native state length overflow"))?;
        if n.saturating_mul(min_item_bytes.max(1)) > self.remaining() && min_item_bytes > 0 {
            return Err(PersistError::new(format!(
                "native state length {n} exceeds the {} bytes left", self.remaining()
            )));
        }
        Ok(n)
    }
}

/// Exact binary persistence for one native type.
pub trait Persist: Sized {
    fn put(&self, w: &mut Writer);
    fn get(r: &mut Reader<'_>) -> Result<Self>;
    /// Appends this type's schema (names and types) to `s`.
    fn schema(s: &mut String);
    /// Lower bound of the encoded size, used to bound length prefixes.
    const MIN_BYTES: usize = 0;
}

/// Schema of a struct field, its type inferred from a field accessor.
pub fn field_schema<S, T: Persist>(_: fn(&S) -> &T, s: &mut String) {
    T::schema(s)
}

macro_rules! persist_le {
    ($($t:ty),*) => {$(
        impl Persist for $t {
            #[inline]
            fn put(&self, w: &mut Writer) {
                w.buf.extend_from_slice(&self.to_le_bytes());
            }
            #[inline]
            fn get(r: &mut Reader<'_>) -> Result<Self> {
                let bytes = r.take(std::mem::size_of::<$t>())?;
                Ok(<$t>::from_le_bytes(bytes.try_into().expect("exact length")))
            }
            fn schema(s: &mut String) {
                s.push_str(stringify!($t));
            }
            const MIN_BYTES: usize = std::mem::size_of::<$t>();
        }
    )*};
}

persist_le!(u8, u16, u32, u64, i8, i16, i32, i64);

impl Persist for usize {
    #[inline]
    fn put(&self, w: &mut Writer) {
        (*self as u64).put(w)
    }
    #[inline]
    fn get(r: &mut Reader<'_>) -> Result<Self> {
        usize::try_from(u64::get(r)?).map_err(|_| PersistError::new("usize overflow in native state"))
    }
    fn schema(s: &mut String) {
        s.push_str("usize");
    }
    const MIN_BYTES: usize = 8;
}

impl Persist for f32 {
    #[inline]
    fn put(&self, w: &mut Writer) {
        self.to_bits().put(w)
    }
    #[inline]
    fn get(r: &mut Reader<'_>) -> Result<Self> {
        Ok(f32::from_bits(u32::get(r)?))
    }
    fn schema(s: &mut String) {
        s.push_str("f32");
    }
    const MIN_BYTES: usize = 4;
}

impl Persist for f64 {
    #[inline]
    fn put(&self, w: &mut Writer) {
        self.to_bits().put(w)
    }
    #[inline]
    fn get(r: &mut Reader<'_>) -> Result<Self> {
        Ok(f64::from_bits(u64::get(r)?))
    }
    fn schema(s: &mut String) {
        s.push_str("f64");
    }
    const MIN_BYTES: usize = 8;
}

impl Persist for bool {
    #[inline]
    fn put(&self, w: &mut Writer) {
        w.buf.push(*self as u8)
    }
    #[inline]
    fn get(r: &mut Reader<'_>) -> Result<Self> {
        match u8::get(r)? {
            0 => Ok(false),
            1 => Ok(true),
            other => Err(PersistError::new(format!("invalid bool {other} in native state"))),
        }
    }
    fn schema(s: &mut String) {
        s.push_str("bool");
    }
    const MIN_BYTES: usize = 1;
}

impl<T: Persist> Persist for Vec<T> {
    fn put(&self, w: &mut Writer) {
        (self.len() as u64).put(w);
        w.buf.reserve(self.len() * T::MIN_BYTES);
        for item in self {
            item.put(w);
        }
    }
    fn get(r: &mut Reader<'_>) -> Result<Self> {
        let n = r.len(T::MIN_BYTES)?;
        let mut out = Vec::with_capacity(n);
        for _ in 0..n {
            out.push(T::get(r)?);
        }
        Ok(out)
    }
    fn schema(s: &mut String) {
        s.push_str("Vec<");
        T::schema(s);
        s.push('>');
    }
    const MIN_BYTES: usize = 8;
}

impl<T: Persist, const N: usize> Persist for [T; N] {
    fn put(&self, w: &mut Writer) {
        for item in self {
            item.put(w);
        }
    }
    fn get(r: &mut Reader<'_>) -> Result<Self> {
        let mut failed: Option<PersistError> = None;
        let items: [Option<T>; N] = std::array::from_fn(|_| {
            if failed.is_some() {
                return None;
            }
            match T::get(r) {
                Ok(v) => Some(v),
                Err(e) => {
                    failed = Some(e);
                    None
                }
            }
        });
        if let Some(e) = failed {
            return Err(e);
        }
        Ok(items.map(|item| item.expect("every element decoded")))
    }
    fn schema(s: &mut String) {
        s.push('[');
        T::schema(s);
        s.push(';');
        s.push_str(&N.to_string());
        s.push(']');
    }
    const MIN_BYTES: usize = T::MIN_BYTES * N;
}

impl<T: Persist> Persist for Option<T> {
    fn put(&self, w: &mut Writer) {
        match self {
            None => w.buf.push(0),
            Some(v) => {
                w.buf.push(1);
                v.put(w);
            }
        }
    }
    fn get(r: &mut Reader<'_>) -> Result<Self> {
        match u8::get(r)? {
            0 => Ok(None),
            1 => Ok(Some(T::get(r)?)),
            other => Err(PersistError::new(format!("invalid option tag {other} in native state"))),
        }
    }
    fn schema(s: &mut String) {
        s.push_str("Option<");
        T::schema(s);
        s.push('>');
    }
    const MIN_BYTES: usize = 1;
}

macro_rules! persist_tuple {
    ($($name:ident),+) => {
        impl<$($name: Persist),+> Persist for ($($name,)+) {
            #[allow(non_snake_case)]
            fn put(&self, w: &mut Writer) {
                let ($($name,)+) = self;
                $($name.put(w);)+
            }
            fn get(r: &mut Reader<'_>) -> Result<Self> {
                Ok(($($name::get(r)?,)+))
            }
            fn schema(s: &mut String) {
                s.push('(');
                $($name::schema(s); s.push(',');)+
                s.push(')');
            }
            const MIN_BYTES: usize = 0 $(+ $name::MIN_BYTES)+;
        }
    };
}

persist_tuple!(A, B);
persist_tuple!(A, B, C);

/// Entries in key order, so equal maps encode to equal bytes. Iteration
/// order of a restored map is the map's own business: no simulation code
/// may depend on `HashMap` iteration order (it differs between processes).
impl<K: Persist + Ord + Hash + Eq, V: Persist> Persist for HashMap<K, V> {
    fn put(&self, w: &mut Writer) {
        let mut entries: Vec<(&K, &V)> = self.iter().collect();
        entries.sort_by(|a, b| a.0.cmp(b.0));
        (entries.len() as u64).put(w);
        for (k, v) in entries {
            k.put(w);
            v.put(w);
        }
    }
    fn get(r: &mut Reader<'_>) -> Result<Self> {
        let n = r.len(K::MIN_BYTES + V::MIN_BYTES)?;
        let mut out = HashMap::with_capacity(n);
        for _ in 0..n {
            let k = K::get(r)?;
            let v = V::get(r)?;
            if out.insert(k, v).is_some() {
                return Err(PersistError::new("duplicate map key in native state"));
            }
        }
        Ok(out)
    }
    fn schema(s: &mut String) {
        s.push_str("Map<");
        K::schema(s);
        s.push(',');
        V::schema(s);
        s.push('>');
    }
    const MIN_BYTES: usize = 8;
}

/// Persist a struct field by field, in the listed order.
///
/// The list must name every field: the struct is destructured without
/// `..`. Fields after `skip` are derived caches that are rebuilt from the
/// persisted state; they are restored as `Default::default()`.
#[macro_export]
macro_rules! persist_struct {
    ($ty:ident { $($f:ident),* $(,)? } $(skip { $($s:ident),* $(,)? })?) => {
        impl $crate::persist::Persist for $ty {
            fn put(&self, w: &mut $crate::persist::Writer) {
                let $ty { $($f,)* $($($s: _,)*)? } = self;
                $( $crate::persist::Persist::put($f, w); )*
            }
            fn get(r: &mut $crate::persist::Reader<'_>) -> $crate::persist::Result<Self> {
                $( let $f = $crate::persist::Persist::get(r)?; )*
                Ok($ty { $($f,)* $($($s: Default::default(),)*)? })
            }
            fn schema(s: &mut String) {
                s.push_str(stringify!($ty));
                s.push('{');
                $(
                    s.push_str(stringify!($f));
                    s.push(':');
                    $crate::persist::field_schema(|x: &$ty| &x.$f, s);
                    s.push(',');
                )*
                $($( s.push_str(concat!("!", stringify!($s), ",")); )*)?
                s.push('}');
            }
        }
    };
}

/// Persist a fieldless enum as one byte per value. The `put` match is
/// exhaustive, so a new variant fails to compile until it is listed.
#[macro_export]
macro_rules! persist_enum {
    ($ty:ident { $($v:ident = $n:literal),* $(,)? }) => {
        impl $crate::persist::Persist for $ty {
            fn put(&self, w: &mut $crate::persist::Writer) {
                let code: u8 = match self { $( $ty::$v => $n, )* };
                w.buf.push(code);
            }
            fn get(r: &mut $crate::persist::Reader<'_>) -> $crate::persist::Result<Self> {
                match <u8 as $crate::persist::Persist>::get(r)? {
                    $( $n => Ok($ty::$v), )*
                    other => Err($crate::persist::PersistError::new(format!(
                        "unknown {} value {} in native state", stringify!($ty), other
                    ))),
                }
            }
            fn schema(s: &mut String) {
                s.push_str(stringify!($ty));
                s.push('(');
                $( s.push_str(concat!(stringify!($v), "=", stringify!($n), ",")); )*
                s.push(')');
            }
            const MIN_BYTES: usize = 1;
        }
    };
}

/// FNV-1a 64 of a schema string.
pub fn fingerprint(schema: &str) -> u64 {
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for b in schema.bytes() {
        h ^= b as u64;
        h = h.wrapping_mul(0x0100_0000_01b3);
    }
    h
}

pub fn schema_of<T: Persist>() -> String {
    let mut s = String::new();
    T::schema(&mut s);
    s
}

/// Encode `value` as a state blob of `kind`.
pub fn encode<T: Persist>(kind: u8, value: &T) -> Vec<u8> {
    let mut w = Writer::new();
    w.buf.extend_from_slice(STATE_MAGIC);
    STATE_VERSION.put(&mut w);
    kind.put(&mut w);
    fingerprint(&schema_of::<T>()).put(&mut w);
    value.put(&mut w);
    w.buf
}

/// Decode a state blob of `kind`, refusing other formats, versions, kinds
/// or layouts, and any trailing bytes.
pub fn decode<T: Persist>(kind: u8, data: &[u8]) -> Result<T> {
    let mut r = Reader::new(data);
    let magic = r.take(8).map_err(|_| PersistError::new("not a native state blob (too short)"))?;
    if magic != STATE_MAGIC {
        return Err(PersistError::new("not a native state blob (bad magic)"));
    }
    let version = u32::get(&mut r)?;
    if version != STATE_VERSION {
        return Err(PersistError::new(format!(
            "native state version {version} is not supported by this build (expects {STATE_VERSION})"
        )));
    }
    let got_kind = u8::get(&mut r)?;
    if got_kind != kind {
        return Err(PersistError::new(format!(
            "native state kind {got_kind} does not match the simulator (expects {kind})"
        )));
    }
    let got = u64::get(&mut r)?;
    let want = fingerprint(&schema_of::<T>());
    if got != want {
        return Err(PersistError::new(format!(
            "native state layout {got:016x} differs from this build's {want:016x}; \
             it was written by an incompatible chronicler_agents build"
        )));
    }
    let value = T::get(&mut r)?;
    if r.remaining() != 0 {
        return Err(PersistError::new(format!(
            "native state has {} trailing bytes", r.remaining()
        )));
    }
    Ok(value)
}

/// Python helpers shared by the three simulators' checkpoint methods.
pub mod py {
    use super::{decode, encode, fingerprint, schema_of, Persist, STATE_VERSION};
    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;
    use pyo3::types::PyBytes;

    pub fn to_bytes<'py, T: Persist>(py: Python<'py>, kind: u8, value: &T) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &encode(kind, value))
    }

    pub fn from_bytes<T: Persist>(kind: u8, data: &[u8]) -> PyResult<T> {
        decode(kind, data).map_err(|e| PyValueError::new_err(e.0))
    }

    /// (state version, layout fingerprint as 16 hex digits, schema string).
    pub fn describe<T: Persist>() -> (u32, String, String) {
        let schema = schema_of::<T>();
        (STATE_VERSION, format!("{:016x}", fingerprint(&schema)), schema)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Debug, PartialEq, Default)]
    struct Sample {
        a: u32,
        b: Vec<[i8; 3]>,
        c: Option<(u16, f32)>,
        d: HashMap<(u16, u16), f32>,
        cache: Option<u8>,
    }
    persist_struct!(Sample { a, b, c, d } skip { cache });

    #[derive(Debug, PartialEq, Clone, Copy)]
    enum Kind {
        One,
        Two,
    }
    persist_enum!(Kind { One = 0, Two = 1 });

    #[test]
    fn round_trip_is_exact() {
        let mut d = HashMap::new();
        d.insert((2, 1), f32::NAN);
        d.insert((1, 9), -0.0);
        let s = Sample { a: 7, b: vec![[1, -2, 3]], c: Some((5, 1.5)), d, cache: Some(9) };
        let blob = encode(KIND_AGENT, &s);
        let back: Sample = decode(KIND_AGENT, &blob).unwrap();
        assert_eq!(back.a, 7);
        assert_eq!(back.b, s.b);
        assert_eq!(back.c, s.c);
        assert_eq!(back.d[&(2, 1)].to_bits(), f32::NAN.to_bits());
        assert_eq!(back.d[&(1, 9)].to_bits(), (-0.0f32).to_bits());
        assert_eq!(back.cache, None);
        // Equal maps encode to equal bytes regardless of insertion order.
        assert_eq!(encode(KIND_AGENT, &back), blob);
    }

    #[test]
    fn refuses_other_kinds_layouts_and_truncation() {
        let blob = encode(KIND_AGENT, &Sample::default());
        assert!(decode::<Sample>(KIND_ECOLOGY, &blob).unwrap_err().0.contains("kind"));
        let mut other = blob.clone();
        other[13] ^= 1; // schema fingerprint
        assert!(decode::<Sample>(KIND_AGENT, &other).unwrap_err().0.contains("layout"));
        assert!(decode::<Sample>(KIND_AGENT, &blob[..blob.len() - 1]).is_err());
        let mut longer = blob.clone();
        longer.push(0);
        assert!(decode::<Sample>(KIND_AGENT, &longer).unwrap_err().0.contains("trailing"));
        assert!(decode::<Sample>(KIND_AGENT, b"CHRNSTA").is_err());
        assert_eq!(Kind::get(&mut Reader::new(&[1])).unwrap(), Kind::Two);
        assert!(Kind::get(&mut Reader::new(&[2])).is_err());
    }

    #[test]
    fn schema_names_fields_types_and_skips() {
        let s = schema_of::<Sample>();
        assert_eq!(
            s,
            "Sample{a:u32,b:Vec<[i8;3]>,c:Option<(u16,f32,)>,d:Map<(u16,u16,),f32>,!cache,}"
        );
    }
}
