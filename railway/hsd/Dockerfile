FROM node:20-alpine AS build

RUN apk add --no-cache bash g++ gcc git gmp-dev make python3 unbound-dev

WORKDIR /opt/hsd

ARG HSD_REPO=https://github.com/shadstoneofficial/hsd.git
ARG HSD_REF=master

RUN git clone --depth=1 --branch="${HSD_REF}" "${HSD_REPO}" .
RUN npm install --omit=dev

FROM node:20-alpine

RUN apk add --no-cache bash gmp-dev unbound-dev

WORKDIR /opt/hsd

COPY --from=build /opt/hsd/bin /opt/hsd/bin
COPY --from=build /opt/hsd/lib /opt/hsd/lib
COPY --from=build /opt/hsd/node_modules /opt/hsd/node_modules
COPY --from=build /opt/hsd/package.json /opt/hsd/package.json
COPY start-hsd.sh /usr/local/bin/start-hsd

RUN chmod +x /usr/local/bin/start-hsd

ENV PATH="/opt/hsd/bin:/opt/hsd/node_modules/.bin:${PATH}"
ENV HSD_PREFIX=/data
ENV HSD_NETWORK=main
ENV HSD_HTTP_HOST=::
ENV HSD_HTTP_PORT=12037
ENV HSD_LOG_LEVEL=info
ENV PORT=12037

EXPOSE 12037

CMD ["start-hsd"]
