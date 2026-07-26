# Frontend image.
#
# Uses Next.js standalone output so the runtime layer carries the compiled
# server and only the dependencies it actually imports, rather than the whole
# node_modules tree.

FROM node:22-bookworm-slim AS deps

WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

# -------------------------------------------------------------------- build --

FROM node:22-bookworm-slim AS builder

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web ./

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ------------------------------------------------------------------ runtime --

FROM node:22-bookworm-slim AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

RUN groupadd --gid 10001 helios && \
    useradd --uid 10001 --gid helios --create-home helios

COPY --from=builder --chown=helios:helios /app/public ./public
COPY --from=builder --chown=helios:helios /app/.next/standalone ./
COPY --from=builder --chown=helios:helios /app/.next/static ./.next/static

USER helios

EXPOSE 3000

CMD ["node", "server.js"]
