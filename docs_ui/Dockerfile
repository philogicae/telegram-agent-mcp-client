# ------------------------------------------------------------
# Multi-stage build for the Next.js app.
# Base image: platformatic/node-caged:26-alpine — Node.js with
# V8 pointer compression enabled (~50% memory reduction for
# pointer-heavy workloads). See https://hub.docker.com/r/platformatic/node-caged
#
# Requires `output: "standalone"` in next.config.mjs so the `runner`
# stage can ship a tiny server bundle without node_modules.
# ------------------------------------------------------------

# Base: shared Node + pnpm toolchain. Pin pnpm to match `packageManager`
# in package.json for reproducible builds.
FROM platformatic/node-caged:26-alpine AS base
ENV PNPM_VERSION=11.17.0 \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /webapp
RUN npm install -g pnpm@${PNPM_VERSION}

# deps: install all dependencies from the lockfile (cached layer)
FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
RUN pnpm install --frozen-lockfile

# builder: compile the Next.js app
FROM base AS builder
COPY --from=deps /webapp/node_modules ./node_modules
COPY . .
RUN pnpm build

# runner: minimal production image, runs the standalone server
FROM platformatic/node-caged:26-alpine AS runner
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=4040 \
    HOSTNAME=0.0.0.0
WORKDIR /webapp

# Non-root user
RUN addgroup --system --gid 1001 nodejs \
    && adduser  --system --uid 1001 nextjs

# Copy the standalone output and its required static assets.
# `.next/standalone` already contains a pruned node_modules subset.
COPY --from=builder --chown=nextjs:nodejs /webapp/public ./public
COPY --from=builder --chown=nextjs:nodejs /webapp/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /webapp/.next/static ./.next/static

USER nextjs
EXPOSE 4040
CMD ["node", "server.js"]
