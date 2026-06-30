FROM node:20-alpine AS base

FROM base AS deps

RUN npm config set registry https://repo.zaris-dev.ir/repository/npm-proxy/ --global

RUN echo "http://mirror.mobinhost.com/alpine/v3.20/main" > /etc/apk/repositories && \
    echo "http://mirror.mobinhost.com/alpine/v3.20/community" >> /etc/apk/repositories && \
    apk update && \
    apk add --no-cache libc6-compat

WORKDIR /app

COPY package.json yarn.lock* package-lock.json* pnpm-lock.yaml* .npmrc* ./

RUN npm ci --include=dev --legacy-peer-deps


FROM base AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV PATH="/app/node_modules/.bin:$PATH"

RUN npm run build


FROM base AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]