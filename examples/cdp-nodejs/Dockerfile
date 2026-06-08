# Connects to a remote Archonum browser over CDP.
# No local browser download needed — we only connect out.
FROM node:24-slim

WORKDIR /app

# We connect to a remote browser, so skip the local Chromium download.
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

COPY package.json ./
RUN npm install --omit=dev

COPY cdp-example.js ./

CMD ["node", "cdp-example.js"]
