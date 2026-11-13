import { defineRailway, github, group, postgres, preserve, project, service } from "railway/iac";

// The app lives in this subdirectory of m5a0r7/job-hunt. Point `branch` at `main`
// once the pull request is merged; until then the working branch is what deploys.
const repo = "m5a0r7/job-hunt";
const branch = "cursor/release-radar-skeleton-7546";

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
    LLM_PROVIDER: "template",
    ANTHROPIC_API_KEY: preserve(),
  };

  const api = service("api", {
    source: github(repo, { branch, rootDirectory: "release-radar" }),
    healthcheck: "/readyz",
    healthcheckTimeout: 120,
    preDeploy: "alembic upgrade head",
    env: {
      ...appEnv,
      // Fixed, so the web service can reach it. Railway healthchecks use this too.
      PORT: "8000",
      // Set this to the web service's public https URL once Railway generates a domain.
      APP_BASE_URL: preserve(),
    },
  });

  const worker = service("worker", {
    source: github(repo, { branch, rootDirectory: "release-radar" }),
    start: "python -m radar.jobs.worker",
    env: appEnv,
  });

  const web = service("web", {
    source: github(repo, { branch, rootDirectory: "release-radar/web" }),
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
