FROM postgres:16-alpine

COPY backup.sh /usr/local/bin/nutrition-bot-backup

ENTRYPOINT ["nutrition-bot-backup"]
