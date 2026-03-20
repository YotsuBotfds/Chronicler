/// M50a Relationship Substrate
/// Per-agent relationship store: BondType enum and classification helpers.

/// Bond types. Values 0-4 match M40 RelationshipType for zero-translation compatibility.
#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BondType {
    // --- Values 0-4 match M40 RelationshipType ---
    Mentor        = 0,   // asymmetric (src = mentor, dst = apprentice)
    Rival         = 1,
    Marriage      = 2,   // reserved, not used until M57
    ExileBond     = 3,
    CoReligionist = 4,
    // --- New types with no M40 equivalent ---
    Kin           = 5,
    Friend        = 6,
    Grudge        = 7,
}

impl BondType {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Mentor),
            1 => Some(Self::Rival),
            2 => Some(Self::Marriage),
            3 => Some(Self::ExileBond),
            4 => Some(Self::CoReligionist),
            5 => Some(Self::Kin),
            6 => Some(Self::Friend),
            7 => Some(Self::Grudge),
            _ => None,
        }
    }
}

pub const REL_SLOTS: usize = 8;
pub const EMPTY_TARGET: u32 = 0;
pub const EMPTY_BOND_TYPE: u8 = 255;

/// Kin bonds are eviction-protected. Marriage joins in M57.
pub fn is_protected(bond_type: u8) -> bool {
    bond_type == BondType::Kin as u8
}

/// Positive-valence bonds strengthen when co-located.
/// Negative-valence bonds (Rival, Grudge) deepen when co-located.
pub fn is_positive_valence(bond_type: u8) -> bool {
    matches!(bond_type, 0 | 2 | 3 | 4 | 5 | 6)
}

/// Only Mentor is asymmetric (single directed entry, src=mentor dst=apprentice).
pub fn is_asymmetric(bond_type: u8) -> bool {
    bond_type == BondType::Mentor as u8
}

pub fn is_symmetric(bond_type: u8) -> bool {
    !is_asymmetric(bond_type)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bond_type_from_u8() {
        assert_eq!(BondType::from_u8(0), Some(BondType::Mentor));
        assert_eq!(BondType::from_u8(5), Some(BondType::Kin));
        assert_eq!(BondType::from_u8(7), Some(BondType::Grudge));
        assert_eq!(BondType::from_u8(8), None);
        assert_eq!(BondType::from_u8(255), None);
    }

    #[test]
    fn test_is_protected() {
        assert!(is_protected(BondType::Kin as u8));
        assert!(!is_protected(BondType::Mentor as u8));
        assert!(!is_protected(BondType::Rival as u8));
        assert!(!is_protected(BondType::Friend as u8));
    }

    #[test]
    fn test_valence() {
        assert!(is_positive_valence(BondType::Kin as u8));
        assert!(is_positive_valence(BondType::Mentor as u8));
        assert!(is_positive_valence(BondType::Friend as u8));
        assert!(is_positive_valence(BondType::CoReligionist as u8));
        assert!(is_positive_valence(BondType::Marriage as u8));
        assert!(is_positive_valence(BondType::ExileBond as u8));
        assert!(!is_positive_valence(BondType::Rival as u8));
        assert!(!is_positive_valence(BondType::Grudge as u8));
    }

    #[test]
    fn test_asymmetry() {
        assert!(is_asymmetric(BondType::Mentor as u8));
        assert!(!is_asymmetric(BondType::Kin as u8));
        assert!(!is_asymmetric(BondType::Rival as u8));
        assert!(is_symmetric(BondType::Kin as u8));
        assert!(is_symmetric(BondType::Rival as u8));
    }

    #[test]
    fn test_m40_value_compatibility() {
        assert_eq!(BondType::Mentor as u8, 0);
        assert_eq!(BondType::Rival as u8, 1);
        assert_eq!(BondType::Marriage as u8, 2);
        assert_eq!(BondType::ExileBond as u8, 3);
        assert_eq!(BondType::CoReligionist as u8, 4);
    }
}
