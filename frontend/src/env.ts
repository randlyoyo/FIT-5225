/**
 * Validate required environment variables on app startup.
 * Logs warnings to console if critical vars are missing.
 */
const requiredVars = [
  "VITE_API_BASE_URL",
  "VITE_GCP_BASE_URL",
  "VITE_COGNITO_USER_POOL_ID",
  "VITE_COGNITO_CLIENT_ID",
] as const;

export function validateEnv(): string[] {
  const missing: string[] = [];
  const defaults: string[] = [];

  for (const key of requiredVars) {
    const val = import.meta.env[key];
    if (!val) {
      missing.push(key);
    } else if (val.includes("xxxxxxxxx") || val.includes("example")) {
      defaults.push(key);
    }
  }

  if (missing.length > 0) {
    console.warn(
      `[AussieEcoLens] Missing env vars: ${missing.join(", ")}. ` +
      `Copy .env.example to .env and fill in your values.`
    );
  }
  if (defaults.length > 0) {
    console.warn(
      `[AussieEcoLens] Env vars still using placeholder values: ${defaults.join(", ")}. ` +
      `Update .env with real values before production use.`
    );
  }

  return [...missing, ...defaults];
}
