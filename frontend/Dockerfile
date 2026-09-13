FROM node:20-alpine

ENV NODE_ENV=development
WORKDIR /app

RUN npm install -g pnpm

# Copy package files
COPY package.json pnpm-lock.yaml ./

# Create pnpm config to allow build scripts
RUN mkdir -p .pnpm
RUN echo "strict-peer-dependencies = false" > .pnpm/config.toml

# Install dependencies (this will approve builds automatically)
RUN pnpm install

# Copy project files
COPY . .

EXPOSE 3000

CMD ["pnpm", "run", "dev"]