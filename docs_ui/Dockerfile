FROM node:24-slim AS base
WORKDIR /frontend
RUN apt-get update && apt-get install -y curl \
    && rm -rf /var/lib/apt/lists/*
RUN npm update -g npm && npm install -g pnpm@latest-10

FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
RUN pnpm install

FROM base AS builder
COPY --from=deps /frontend/node_modules ./node_modules
COPY . .
RUN chmod +x /frontend/node_modules/.bin/next
RUN pnpm exec next telemetry disable
RUN pnpm run build

FROM base AS runner
COPY --from=deps /frontend/node_modules ./node_modules
COPY --from=builder /frontend/out ./out
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
EXPOSE 4040
CMD ["pnpm", "run", "serve"]
