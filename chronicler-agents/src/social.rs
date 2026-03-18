/// Relationship type enum — matches Python-side constants.
#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RelationshipType {
    Mentor = 0,
    Rival = 1,
    Marriage = 2,
    ExileBond = 3,
    CoReligionist = 4,
}

impl RelationshipType {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Mentor),
            1 => Some(Self::Rival),
            2 => Some(Self::Marriage),
            3 => Some(Self::ExileBond),
            4 => Some(Self::CoReligionist),
            _ => None,
        }
    }
}

/// A single social relationship between two named characters.
///
/// Directionality:
/// - Mentor: agent_a = mentor, agent_b = apprentice (asymmetric)
/// - All others: agent_a < agent_b by convention (symmetric)
#[derive(Debug, Clone)]
pub struct SocialEdge {
    pub agent_a: u32,
    pub agent_b: u32,
    pub relationship: RelationshipType,
    pub formed_turn: u16,
}

/// Social graph owned by AgentSimulator. Relationships cross region boundaries.
/// Capacity hint: 512 edges (~6KB). Named-character-only, max ~50 chars × ~10 edges.
pub struct SocialGraph {
    pub edges: Vec<SocialEdge>,
}

impl SocialGraph {
    pub fn new() -> Self {
        Self {
            edges: Vec::with_capacity(512),
        }
    }

    pub fn clear(&mut self) {
        self.edges.clear();
    }

    pub fn replace(&mut self, new_edges: Vec<SocialEdge>) {
        self.edges = new_edges;
    }

    pub fn edge_count(&self) -> usize {
        self.edges.len()
    }
}
