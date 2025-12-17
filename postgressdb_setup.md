docker run --name gov-postgres \
  -e POSTGRES_USER=govuser \
  -e POSTGRES_PASSWORD=govpass \
  -e POSTGRES_DB=govdb \
  -p 5432:5432 \
  -d postgres:16


docker exec -it gov-postgres psql -U govuser -d govdb
