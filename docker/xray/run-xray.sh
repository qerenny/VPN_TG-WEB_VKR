#!/bin/sh
set -eu

XRAY_CONFIG_PATH="/tmp/xray-config.json"

url_decode() {
  printf '%b' "$(printf '%s' "$1" | sed 's/+/ /g; s/%/\\x/g')"
}

render_direct_config() {
  cat >"$XRAY_CONFIG_PATH" <<'EOF'
{
  "log": {
    "access": "/dev/null",
    "error": "/dev/stderr",
    "loglevel": "none"
  },
  "inbounds": [
    {
      "tag": "telegram-http-proxy",
      "listen": "0.0.0.0",
      "port": 8080,
      "protocol": "http",
      "settings": {}
    }
  ],
  "outbounds": [
    {
      "tag": "direct",
      "protocol": "freedom",
      "settings": {}
    }
  ]
}
EOF
}

render_vless_config() {
  raw_url="$1"
  stripped_url="${raw_url#vless://}"
  without_fragment="${stripped_url%%#*}"

  case "$without_fragment" in
    *\?*)
      authority="${without_fragment%%\?*}"
      query="${without_fragment#*\?}"
      ;;
    *)
      echo "TELEGRAM_VLESS_URL is missing query parameters." >&2
      exit 1
      ;;
  esac

  case "$authority" in
    *@*:*)
      uuid="${authority%@*}"
      hostport="${authority#*@}"
      host="${hostport%:*}"
      port="${hostport##*:}"
      ;;
    *)
      echo "TELEGRAM_VLESS_URL has invalid authority section." >&2
      exit 1
      ;;
  esac

  flow=""
  security=""
  transport_type=""
  fingerprint=""
  server_name=""
  public_key=""
  short_id=""
  spider_x="/"
  encryption="none"

  OLD_IFS=$IFS
  IFS='&'
  set -- $query
  IFS=$OLD_IFS

  for kv in "$@"; do
    key="${kv%%=*}"
    value=""
    if [ "$kv" != "$key" ]; then
      value="${kv#*=}"
    fi
    value="$(url_decode "$value")"

    case "$key" in
      type) transport_type="$value" ;;
      security) security="$value" ;;
      pbk) public_key="$value" ;;
      fp) fingerprint="$value" ;;
      sni) server_name="$value" ;;
      sid) short_id="$value" ;;
      spx) spider_x="$value" ;;
      flow) flow="$value" ;;
      encryption) encryption="$value" ;;
    esac
  done

  if [ "$transport_type" != "tcp" ]; then
    echo "Only VLESS TCP transport is supported for TELEGRAM_VLESS_URL." >&2
    exit 1
  fi

  if [ "$security" != "reality" ]; then
    echo "Only VLESS Reality links are supported for TELEGRAM_VLESS_URL." >&2
    exit 1
  fi

  if [ -z "$uuid" ] || [ -z "$host" ] || [ -z "$port" ] || [ -z "$public_key" ] || [ -z "$server_name" ] || [ -z "$fingerprint" ]; then
    echo "TELEGRAM_VLESS_URL is missing required VLESS Reality fields." >&2
    exit 1
  fi

  flow_json=""
  if [ -n "$flow" ]; then
    flow_json=$(cat <<EOF
,
                "flow": "$flow"
EOF
)
  fi

  cat >"$XRAY_CONFIG_PATH" <<EOF
{
  "log": {
    "access": "/dev/null",
    "error": "/dev/stderr",
    "loglevel": "none"
  },
  "inbounds": [
    {
      "tag": "telegram-http-proxy",
      "listen": "0.0.0.0",
      "port": 8080,
      "protocol": "http",
      "settings": {}
    }
  ],
  "outbounds": [
    {
      "tag": "telegram-vless",
      "protocol": "vless",
      "settings": {
        "vnext": [
          {
            "address": "$host",
            "port": $port,
            "users": [
              {
                "id": "$uuid",
                "encryption": "$encryption"$flow_json
              }
            ]
          }
        ]
      },
      "streamSettings": {
        "network": "$transport_type",
        "security": "$security",
        "realitySettings": {
          "show": false,
          "fingerprint": "$fingerprint",
          "serverName": "$server_name",
          "publicKey": "$public_key",
          "shortId": "$short_id",
          "spiderX": "$spider_x"
        }
      }
    }
  ]
}
EOF
}

TELEGRAM_VLESS_URL="${TELEGRAM_VLESS_URL:-}"

if [ -n "$TELEGRAM_VLESS_URL" ]; then
  render_vless_config "$TELEGRAM_VLESS_URL"
else
  render_direct_config
fi

if [ "${XRAY_VALIDATE_ONLY:-0}" = "1" ]; then
  cat "$XRAY_CONFIG_PATH"
  exit 0
fi

exec xray run -c "$XRAY_CONFIG_PATH" >/dev/null
