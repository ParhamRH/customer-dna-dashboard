# Brand DNA dashboard (Next.js, standalone output).
# BDNA_API_INTERNAL_URL is read by next.config.ts rewrites at BUILD time: it is where the web
# container forwards same-origin /v1/* requests (behind Caddy, /v1/* goes to the API directly).
FROM node:22-alpine AS deps
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1
ARG BDNA_API_INTERNAL_URL=http://api:8000
ENV BDNA_API_INTERNAL_URL=$BDNA_API_INTERNAL_URL
COPY --from=deps /web/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S web && adduser -S -G web web
COPY --from=build --chown=web:web /web/.next/standalone ./
COPY --from=build --chown=web:web /web/.next/static ./.next/static
USER web
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD wget -qO- http://127.0.0.1:3000/login >/dev/null || exit 1
CMD ["node", "server.js"]
