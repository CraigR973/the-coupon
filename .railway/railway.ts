import { defineRailway, preserve, project, service } from "railway/iac";

// This repository owns the `api` service in each Coupon Railway project, and declares the
// `payments` service (ADR 0009 option B) for the projects switched on below. A named partial
// keeps IaC from treating resources outside this file as deletions.
export const partial = "api";

export const DEPLOYMENT_INVARIANTS = {
  "builder": "NIXPACKS",
  "nixpacksConfigPath": "nixpacks.toml",
  "healthcheckPath": "/api/v1/health/ready",
  "healthcheckTimeout": 300,
  "numReplicas": 1,
  "sleepApplication": false,
  "ipv6EgressEnabled": true,
  "multiRegionConfig": {
    "europe-west4-drams3a": {
      "numReplicas": 1
    }
  },
  "restartPolicyType": "ON_FAILURE",
  "restartPolicyMaxRetries": 3
} as const;

// Batch 207. The second process: the only one that will hold the Monzo token (Batch 208).
// It never runs Alembic. `python -m src.payments_service` refuses to start unless the
// database is at exactly the migration head bundled in its image, so the API, which
// migrates on boot, ships first. One replica, because Batch 208's token refresh rotates the
// refresh token and two processes refreshing would revoke each other.
export const PAYMENTS_DEPLOYMENT_INVARIANTS = {
  "builder": "NIXPACKS",
  "nixpacksConfigPath": "nixpacks.toml",
  "startCommand": "python -m src.payments_service",
  "healthcheckPath": "/health/ready",
  "healthcheckTimeout": 300,
  "numReplicas": 1,
  "sleepApplication": false,
  "ipv6EgressEnabled": true,
  "multiRegionConfig": {
    "europe-west4-drams3a": {
      "numReplicas": 1
    }
  },
  "restartPolicyType": "ON_FAILURE",
  "restartPolicyMaxRetries": 3
} as const;

// Owner decision, 2026-10-14: declared but switched off in both projects, so no plan
// creates it. The owner then created production's service and sealed its variables (id in
// docs/agent-commands/ship-prod.md), and switched production on (owner, 2026-10-15). Staging
// stays off.
export const PAYMENTS_SERVICE_ENABLED = {
  "the-coupon-staging": false,
  "the-coupon-production": true
} as const;

// Each project's payments origin, recorded in the same commit that switches it on.
// `scripts/check-deploy-drift.sh` reads production's from origin/main, so recording it needs
// no change to that protected script.
export const PAYMENTS_ORIGINS = {
  "the-coupon-staging": "",
  "the-coupon-production": "https://payments-production-0aa1.up.railway.app"
} as const;

// Sealed by the owner when the service is created; preserve() keeps them that way.
export const PAYMENTS_PRESERVED_VARIABLE_NAMES = [
  "DATABASE_URL",
  "ENVIRONMENT",
  "LOG_LEVEL",
  "MONZO_CLIENT_ID",
  "MONZO_CLIENT_SECRET",
  "MONZO_TOKEN_ENCRYPTION_KEY",
  "MONZO_WEBHOOK_PATH_SECRET",
  "RAILWAY_GIT_COMMIT_SHA",
] as const;

const TARGETS = {
  "cc2fc994-87c3-4e2e-8d9b-5bcafa496350": {
    environmentId: "333ffc77-ad0d-43af-8436-4865fb9c2946",
    projectName: "the-coupon-staging",
  },
  "e030ebe3-e7fc-43c9-9478-4e80cafaa126": {
    environmentId: "8f18cb49-5137-4557-900a-031bcab4ac38",
    projectName: "the-coupon-production",
  },
} as const;

// IaC replaces the service's environment as a set. preserve() keeps live values sealed
// while making omission unable to delete them. A newly added Railway variable must be
// added here before the next config apply; an omission is destructive and the ship
// workflows deliberately refuse destructive plans.
export const PRESERVED_VARIABLE_NAMES = [
  "AVATAR_STORAGE",
  "BF_APP_KEY",
  "BF_CERT_FILE",
  "BF_CERT_PEM_B64",
  "BF_FAKE_MODE",
  "BF_KEY_FILE",
  "BF_KEY_PEM_B64",
  "BF_PASS",
  "BF_USER",
  "DATABASE_URL",
  "ENVIRONMENT",
  "FOOTBALL_API_KEY",
  "FOOTBALL_DATA_PROVIDER",
  "FRONTEND_ORIGIN",
  "JWT_ACCESS_SECRET",
  "JWT_REFRESH_SECRET",
  "LOG_LEVEL",
  "ODDS_API_BOOKMAKER",
  "ODDS_API_KEY",
  "ODDS_PROVIDER",
  "RAILWAY_GIT_COMMIT_SHA",
  "SCHEDULER_ENABLED",
  "SUPABASE_SERVICE_KEY",
  "SUPABASE_URL",
  "VAPID_CONTACT_EMAIL",
  "VAPID_PRIVATE_KEY",
  "VAPID_PUBLIC_KEY",
] as const;

export default defineRailway((ctx) => {
  const target = TARGETS[ctx.projectId as keyof typeof TARGETS];
  if (!target || ctx.environmentId !== target.environmentId) {
    throw new Error(
      `Refusing Railway IaC target ${ctx.projectId ?? "unknown"}/${ctx.environmentId ?? "unknown"}`,
    );
  }

  const api = service("api", {
    build: {
      builder: DEPLOYMENT_INVARIANTS.builder,
      buildEnvironment: "V3",
      nixpacksConfigPath: DEPLOYMENT_INVARIANTS.nixpacksConfigPath,
    },
    deploy: {
      healthcheckPath: DEPLOYMENT_INVARIANTS.healthcheckPath,
      healthcheckTimeout: DEPLOYMENT_INVARIANTS.healthcheckTimeout,
      numReplicas: DEPLOYMENT_INVARIANTS.numReplicas,
      sleepApplication: DEPLOYMENT_INVARIANTS.sleepApplication,
      ipv6EgressEnabled: DEPLOYMENT_INVARIANTS.ipv6EgressEnabled,
      multiRegionConfig: DEPLOYMENT_INVARIANTS.multiRegionConfig,
      restartPolicyType: DEPLOYMENT_INVARIANTS.restartPolicyType,
      restartPolicyMaxRetries: DEPLOYMENT_INVARIANTS.restartPolicyMaxRetries,
      runtime: "V2",
      useLegacyStacker: false,
      limitOverride: {
        containers: {
          cpu: 0.25,
          memoryBytes: 500_000_000,
        },
      },
    },
    env: Object.fromEntries(PRESERVED_VARIABLE_NAMES.map((name) => [name, preserve()])),
  });

  const resources = PAYMENTS_SERVICE_ENABLED[target.projectName] ? [api, paymentsService()] : [api];
  return project(target.projectName, { resources });
});

export function paymentsService() {
  return service("payments", {
    build: {
      builder: PAYMENTS_DEPLOYMENT_INVARIANTS.builder,
      buildEnvironment: "V3",
      nixpacksConfigPath: PAYMENTS_DEPLOYMENT_INVARIANTS.nixpacksConfigPath,
    },
    deploy: {
      startCommand: PAYMENTS_DEPLOYMENT_INVARIANTS.startCommand,
      healthcheckPath: PAYMENTS_DEPLOYMENT_INVARIANTS.healthcheckPath,
      healthcheckTimeout: PAYMENTS_DEPLOYMENT_INVARIANTS.healthcheckTimeout,
      numReplicas: PAYMENTS_DEPLOYMENT_INVARIANTS.numReplicas,
      sleepApplication: PAYMENTS_DEPLOYMENT_INVARIANTS.sleepApplication,
      ipv6EgressEnabled: PAYMENTS_DEPLOYMENT_INVARIANTS.ipv6EgressEnabled,
      multiRegionConfig: PAYMENTS_DEPLOYMENT_INVARIANTS.multiRegionConfig,
      restartPolicyType: PAYMENTS_DEPLOYMENT_INVARIANTS.restartPolicyType,
      restartPolicyMaxRetries: PAYMENTS_DEPLOYMENT_INVARIANTS.restartPolicyMaxRetries,
      runtime: "V2",
      useLegacyStacker: false,
      limitOverride: {
        containers: {
          cpu: 0.25,
          memoryBytes: 500_000_000,
        },
      },
    },
    env: Object.fromEntries(PAYMENTS_PRESERVED_VARIABLE_NAMES.map((name) => [name, preserve()])),
  });
}
