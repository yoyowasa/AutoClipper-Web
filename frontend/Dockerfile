FROM node:20-bookworm-slim

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json ./
COPY frontend/package.json ./frontend/package.json
RUN npm ci --workspace frontend

COPY frontend ./frontend

EXPOSE 3000

CMD ["npm", "--workspace", "frontend", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
