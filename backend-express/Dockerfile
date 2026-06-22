# ─────────────────────────────────────────────────────────────
# LUMINA Express backend (API gateway, Sequelize, Clerk auth)
# ─────────────────────────────────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
# Production deps only (nodemon is the only devDependency).
RUN npm ci --omit=dev

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN apk add --no-cache curl

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# server.js reads process.env.PORT (default 4000). PaaS inject $PORT.
ENV PORT=4000
EXPOSE 4000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/" || exit 1

CMD ["node", "server.js"]
