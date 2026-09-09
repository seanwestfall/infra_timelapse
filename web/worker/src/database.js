import { neon } from "@neondatabase/serverless";

const SCHEMA = "infratimelapse";

const QUERIES = {
  nodes: async (sql) => sql`
    SELECT
      e.code,
      e.canonical_name AS name,
      e.record_status::text AS record_status,
      n.node_type::text AS node_type,
      n.monitoring_tier::text AS monitoring_tier,
      COALESCE(
        (
          SELECT jsonb_agg(
            jsonb_build_object(
              'iso2', btrim(j.country_iso2),
              'role', j.jurisdiction_role::text
            )
            ORDER BY btrim(j.country_iso2), j.jurisdiction_role::text
          )
          FROM infratimelapse.node_jurisdictions AS j
          WHERE j.node_id = n.entity_id
        ),
        '[]'::jsonb
      ) AS jurisdictions,
      (
        SELECT ST_AsGeoJSON(g.geom)::jsonb
        FROM infratimelapse.node_geometries AS g
        WHERE g.node_id = n.entity_id
          AND g.geometry_role = 'centroid'
          AND g.is_current
        ORDER BY g.created_at DESC, g.geometry_id
        LIMIT 1
      ) AS geometry
    FROM infratimelapse.nodes AS n
    JOIN infratimelapse.entities AS e ON e.entity_id = n.entity_id
    WHERE e.record_status <> 'deprecated'
    ORDER BY e.code
  `,
  corridors: async (sql) => sql`
    SELECT
      e.code,
      e.canonical_name AS name,
      e.record_status::text AS record_status,
      c.corridor_type::text AS corridor_type,
      c.service_pattern::text AS service_pattern,
      (
        SELECT ST_AsGeoJSON(g.route_geometry)::jsonb
        FROM infratimelapse.corridor_geometries AS g
        WHERE g.corridor_id = c.entity_id
          AND g.is_current
        ORDER BY
          CASE g.geometry_role::text
            WHEN 'primary' THEN 0
            WHEN 'alternative' THEN 1
            ELSE 2
          END,
          g.branch_code,
          g.created_at DESC
        LIMIT 1
      ) AS geometry,
      COALESCE(
        (
          SELECT jsonb_agg(
            jsonb_build_object(
              'code', node_entity.code,
              'role', membership.role::text,
              'membership_type', membership.membership_type::text,
              'branch_code', membership.branch_code,
              'sequence_no', membership.sequence_no
            )
            ORDER BY
              membership.branch_code,
              membership.sequence_no NULLS LAST,
              node_entity.code,
              membership.role::text
          )
          FROM infratimelapse.corridor_nodes AS membership
          JOIN infratimelapse.entities AS node_entity
            ON node_entity.entity_id = membership.node_id
          WHERE membership.corridor_id = c.entity_id
            AND node_entity.record_status <> 'deprecated'
        ),
        '[]'::jsonb
      ) AS nodes
    FROM infratimelapse.corridors AS c
    JOIN infratimelapse.entities AS e ON e.entity_id = c.entity_id
    WHERE e.record_status <> 'deprecated'
    ORDER BY e.code
  `,
  projects: async (sql) => sql`
    SELECT
      e.code,
      e.canonical_name AS name,
      e.record_status::text AS record_status,
      p.project_type::text AS project_type,
      (
        SELECT jsonb_build_object(
          'status', history.lifecycle_status::text,
          'assertion_status', history.assertion_status::text,
          'status_as_of', history.status_as_of
        )
        FROM infratimelapse.entity_status_history AS history
        WHERE history.entity_id = p.entity_id
          AND history.effective_to IS NULL
        ORDER BY history.status_as_of DESC, history.created_at DESC
        LIMIT 1
      ) AS lifecycle,
      COALESCE(
        (
          SELECT jsonb_agg(
            jsonb_build_object(
              'code', node_entity.code,
              'role', project_node.role::text
            )
            ORDER BY node_entity.code, project_node.role::text
          )
          FROM infratimelapse.project_nodes AS project_node
          JOIN infratimelapse.entities AS node_entity
            ON node_entity.entity_id = project_node.node_id
          WHERE project_node.project_id = p.entity_id
            AND node_entity.record_status <> 'deprecated'
        ),
        '[]'::jsonb
      ) AS nodes
    FROM infratimelapse.projects AS p
    JOIN infratimelapse.entities AS e ON e.entity_id = p.entity_id
    WHERE e.record_status <> 'deprecated'
    ORDER BY e.code
  `,
};

export const DATABASE_PATHS = new Map([
  ["/api/nodes", "nodes"],
  ["/api/corridors", "corridors"],
  ["/api/projects", "projects"],
]);

export async function queryInventory(kind, databaseUrl, createClient = neon) {
  if (!databaseUrl) throw new Error("DATABASE_URL is not configured");
  const query = QUERIES[kind];
  if (!query) throw new Error("Unknown inventory query");
  const sql = createClient(databaseUrl);
  const rows = await query(sql);
  return {
    schema: SCHEMA,
    count: rows.length,
    data: rows,
  };
}
