FROM node:20-slim

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    SHARE_STORAGE_DIR=/app/storage

COPY package*.json ./
RUN npm install --legacy-peer-deps

COPY . .

RUN mkdir -p /app/storage/files /app/storage/trash /app/storage/uploads /app/storage/access-hub \
    && npm run build

ENV NODE_ENV=production

EXPOSE 3000

CMD ["sh", "-c", "node scripts/bootstrap-storage.mjs --background && npx next start -H 0.0.0.0 -p 3000"]
