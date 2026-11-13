import { defineRailway, github, group, postgres, preserve, project, service } from "railway/iac";

// Standalone private repo. The API builds from the repository root and the web app from web/.
const repo = "m5a0r7/release-radar";
const branch = "main";

export default defineRailway(() => {
  const db = postgres("Postgres");

  // Shared by the API and the worker. GITHUB_TOKEN and ANTHROPIC_API_KEY are set in the
  // Railway dashboard; preserve() keeps those values out of this file.
  const appEnv = {
    DATABASE_URL: db.env.DATABASE_URL,
    ENVIRONMENT: "production",
    AUTH_DEV_LOGIN: "true",
    // Last UTC day the shared demo account accepts sign-ins. Edit to extend the trial.
    DEMO_UNTIL: "2026-12-12",
    SESSION_COOKIE_SECURE: "true",
    GITHUB_TOKEN: preserve(),
    // Set on the api service in the dashboard. A fixed value here is reapplied on
    // every config deploy and turns the model back off.
    LLM_PROVIDER: preserve(),
    ANTHROPIC_API_KEY: preserve(),
    ANTHROPIC_MODEL: preserve(),
  };

  const api = service("api", {
    source: github(repo, { branch }),
    healthcheck: "/readyz",
    healthcheckTimeout: 120,
    preDeploy: "alembic upgrade head",
    env: {
      ...appEnv,
      // Fixed, so the web service can reach it. Railway healthchecks use this too.
      PORT: "8000",
      // Browser origin. GitHub returns to APP_BASE_URL/v1/auth/github/callback.
      APP_BASE_URL: "https://${{web.RAILWAY_PUBLIC_DOMAIN}}",
      // Create the OAuth app in GitHub settings, then paste both values in the dashboard.
      GITHUB_OAUTH_CLIENT_ID: preserve(),
      GITHUB_OAUTH_CLIENT_SECRET: preserve(),
    },
  });

  const worker = service("worker", {
    source: github(repo, { branch }),
    start: "python -m radar.jobs.worker",
    env: appEnv,
  });

  const web = service("web", {
    source: github(repo, { branch, rootDirectory: "web" }),
    healthcheck: "/",
    env: {
      // Railway injects PORT for this service; nginx listens on it.
      API_HOST: api.env.RAILWAY_PRIVATE_DOMAIN,
    },
  });

  return project("release-radar", {
    resources: [group("Release Radar", [db, api, worker, web])],
  });
});
