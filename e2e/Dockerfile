FROM mcr.microsoft.com/playwright:v1.64.1-noble

WORKDIR /tests

COPY package.json package-lock.json ./
RUN npm ci

COPY playwright.config.ts ./
COPY tests ./tests

CMD ["npm", "test"]
