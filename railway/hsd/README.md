# Railway HSD Service

This service runs a private full HSD node for LearnHNS Market.

It is intended for backend-only marketplace support:

- LearnHNS Market calls HSD over Railway private networking.
- Bob Wallet users do not call this node directly.
- The service should not have a public Railway domain.
- Chain data is stored on a Railway persistent volume mounted at `/data`.

## Railway Variables

Set these on the HSD service:

```txt
HSD_API_KEY=<secret>
PORT=12037
HSD_HTTP_PORT=12037
HSD_HTTP_HOST=::
HSD_PREFIX=/data
HSD_NETWORK=main
HSD_LOG_LEVEL=info
```

Set these on the LearnHNS Market app service:

```txt
HSD_HTTP_URL=http://learnhns-hsd.railway.internal:12037
HSD_API_KEY=<same secret as HSD service>
```

Railway private networking uses service DNS names like:

```txt
<service-name>.railway.internal
```

Use `http://` for private service-to-service traffic.

## Deploy

Deploy this folder as the Railway service root so Railway uses the HSD Dockerfile instead of the main market app Dockerfile:

```txt
railway up railway/hsd --service learnhns-hsd --detach --path-as-root
```
