"""Cypher query templates for the knowledge graph.

Every query is a parameterised constant string.  All domain queries include a
``WHERE n.user_id = $user_id`` clause (or equivalent) to enforce strict
per-tenant isolation.
"""

from __future__ import annotations

# ===================================================================
# Node CRUD
# ===================================================================

# Parameters: $user_id, $label (injected via f-string), $id, $props
# NOTE: ``$label`` is NOT parameterisable in Cypher -- it must be
#       interpolated into the query string **before** execution.
#       All other values go through driver-level parameterisation.

CREATE_NODE: str = (
    "CREATE (n:{label} {{id: $id, user_id: $user_id}}) "
    "SET n += $props "
    "RETURN n"
)

READ_NODE: str = (
    "MATCH (n) "
    "WHERE n.id = $id AND n.user_id = $user_id "
    "RETURN n"
)

UPDATE_NODE: str = (
    "MATCH (n) "
    "WHERE n.id = $id AND n.user_id = $user_id "
    "SET n += $props "
    "RETURN n"
)

DELETE_NODE: str = (
    "MATCH (n) "
    "WHERE n.id = $id AND n.user_id = $user_id "
    "DETACH DELETE n "
    "RETURN count(n) AS deleted"
)

# ===================================================================
# Edge CRUD
# ===================================================================

# Parameters: $user_id, $source_id, $target_id, $props
# ``{rel_type}`` is string-interpolated (relationship types are not
# parameterisable in Cypher).

CREATE_EDGE: str = (
    "MATCH (a), (b) "
    "WHERE a.id = $source_id AND a.user_id = $user_id "
    "  AND b.id = $target_id AND b.user_id = $user_id "
    "CREATE (a)-[r:{rel_type} {{user_id: $user_id}}]->(b) "
    "SET r += $props "
    "RETURN type(r) AS rel_type, properties(r) AS props, "
    "       a.id AS source_id, b.id AS target_id"
)

GET_EDGES: str = (
    "MATCH (n)-[r]-(m) "
    "WHERE n.id = $node_id AND n.user_id = $user_id "
    "  AND m.user_id = $user_id "
    "RETURN type(r) AS rel_type, properties(r) AS props, "
    "       startNode(r).id AS source_id, endNode(r).id AS target_id"
)

DELETE_EDGE: str = (
    "MATCH (a)-[r:{rel_type}]->(b) "
    "WHERE a.id = $source_id AND a.user_id = $user_id "
    "  AND b.id = $target_id AND b.user_id = $user_id "
    "DELETE r "
    "RETURN count(r) AS deleted"
)

# ===================================================================
# Search
# ===================================================================

# Fulltext search scoped to a user.
# Parameters: $user_id, $query, $limit

FULLTEXT_SEARCH: str = (
    "CALL db.index.fulltext.queryNodes($index_name, $query) "
    "YIELD node, score "
    "WHERE node.user_id = $user_id "
    "RETURN node, score "
    "ORDER BY score DESC "
    "LIMIT $limit"
)

# ===================================================================
# Stats
# ===================================================================

# Count nodes per label for a given user.
# Parameters: $user_id
# ``{label}`` is string-interpolated.

COUNT_NODES_BY_LABEL: str = (
    "MATCH (n:{label}) "
    "WHERE n.user_id = $user_id "
    "RETURN count(n) AS count"
)

COUNT_EDGES: str = (
    "MATCH (n)-[r]-() "
    "WHERE n.user_id = $user_id "
    "RETURN count(r) AS count"
)

# ===================================================================
# Traversal
# ===================================================================

# Variable-length BFS from a given node.
# Parameters: $user_id, $node_id, $max_hops
# ``{rel_filter}`` is optionally string-interpolated to restrict
# relationship types (e.g. ":RELATED_TO|SUPPORTS").

GET_NEIGHBORS: str = (
    "MATCH path = (start)-[{rel_filter}*1..{max_hops}]-(neighbor) "
    "WHERE start.id = $node_id AND start.user_id = $user_id "
    "  AND neighbor.user_id = $user_id "
    "UNWIND relationships(path) AS r "
    "WITH DISTINCT neighbor, r "
    "RETURN neighbor, type(r) AS rel_type, "
    "       startNode(r).id AS source_id, endNode(r).id AS target_id"
)
