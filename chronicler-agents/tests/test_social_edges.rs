use chronicler_agents::{RelationshipType, SocialEdge, SocialGraph};

#[test]
fn test_social_graph_replace() {
    let mut graph = SocialGraph::new();
    assert_eq!(graph.edge_count(), 0);

    let edges = vec![
        SocialEdge {
            agent_a: 100,
            agent_b: 200,
            relationship: RelationshipType::Rival,
            formed_turn: 50,
        },
        SocialEdge {
            agent_a: 100,
            agent_b: 300,
            relationship: RelationshipType::Mentor,
            formed_turn: 60,
        },
    ];
    graph.replace(edges);
    assert_eq!(graph.edge_count(), 2);
    assert_eq!(graph.edges[0].relationship, RelationshipType::Rival);
    assert_eq!(graph.edges[1].agent_a, 100);
    assert_eq!(graph.edges[1].agent_b, 300);
}

#[test]
fn test_social_graph_clear() {
    let mut graph = SocialGraph::new();
    graph.replace(vec![SocialEdge {
        agent_a: 1,
        agent_b: 2,
        relationship: RelationshipType::Marriage,
        formed_turn: 10,
    }]);
    assert_eq!(graph.edge_count(), 1);
    graph.clear();
    assert_eq!(graph.edge_count(), 0);
}

#[test]
fn test_relationship_type_from_u8() {
    assert_eq!(RelationshipType::from_u8(0), Some(RelationshipType::Mentor));
    assert_eq!(RelationshipType::from_u8(4), Some(RelationshipType::CoReligionist));
    assert_eq!(RelationshipType::from_u8(5), None);
}
