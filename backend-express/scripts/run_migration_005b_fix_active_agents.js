import { Sequelize } from "sequelize";
import dotenv from "dotenv";
dotenv.config();

const DATABASE_URL =
  process.env.DATABASE_URL ||
  "postgresql://postgres:admin@localhost:5432/FYP_backup";

const sequelize = new Sequelize(DATABASE_URL, { dialect: "postgres", logging: false });

async function run() {
  await sequelize.authenticate();

  // Check current type
  const [cols] = await sequelize.query(
    "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'initial_profiles' AND column_name = 'active_agents'"
  );
  const currentType = cols[0]?.data_type;
  console.log("active_agents current type:", currentType);

  if (currentType === "ARRAY" || currentType?.includes("text")) {
    console.log("✓ active_agents is already TEXT[] — nothing to do.");
    await sequelize.close();
    return;
  }

  // json/jsonb → text[] using string manipulation
  // JSON array ["academic","wellness"] → Postgres text-array literal {academic,wellness}
  await sequelize.query(`
    ALTER TABLE initial_profiles
      ALTER COLUMN active_agents TYPE TEXT[]
      USING (
        CASE
          WHEN active_agents IS NULL
            THEN ARRAY['academic']::TEXT[]
          ELSE
            string_to_array(
              TRIM(BOTH '[]' FROM REPLACE(active_agents::TEXT, '"', '')),
              ','
            )
        END
      );
  `);
  console.log("✓ active_agents converted to TEXT[]");
  await sequelize.close();
}

run().catch((err) => {
  console.error("Failed:", err.message);
  process.exit(1);
});
