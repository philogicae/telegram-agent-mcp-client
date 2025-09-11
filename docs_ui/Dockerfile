FROM node:24-alpine AS base
WORKDIR /frontend
RUN npm update -g npm && npm install -g pnpm@latest-10

FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
RUN pnpm install --frozen-lockfile

FROM base AS runner
COPY --from=deps /frontend/node_modules ./node_modules
COPY . .
RUN chmod +x /frontend/node_modules/.bin/next
RUN pnpm exec next telemetry disable
RUN pnpm build
EXPOSE 4040
CMD ["pnpm", "start"]
