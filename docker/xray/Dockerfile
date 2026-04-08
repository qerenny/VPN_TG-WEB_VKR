FROM ghcr.io/xtls/xray-core:latest AS xray-bin

FROM alpine:3.20

RUN apk add --no-cache ca-certificates

COPY --from=xray-bin /usr/local/bin/xray /usr/local/bin/xray
COPY ./run-xray.sh /etc/xray/run-xray.sh

RUN chmod +x /etc/xray/run-xray.sh /usr/local/bin/xray

ENTRYPOINT ["/bin/sh", "/etc/xray/run-xray.sh"]
