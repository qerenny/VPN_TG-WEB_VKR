FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files and install dependencies first (caching)
COPY ./frontend/package*.json ./
RUN npm install

# Copy frontend source, including Vite env files
COPY ./frontend ./

# Build
RUN npm run build

FROM nginx:alpine AS deployer
RUN rm -rf /usr/share/nginx/html/*
COPY --from=builder /app/dist /usr/share/nginx/html

CMD ["echo", "Built frontend. Copy /usr/share/nginx/html → /var/www/nowmeow"]
