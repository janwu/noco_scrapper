# Vaadin web app (webapp/) in production mode. The database is not in the
# image: compose mounts ./db, the app reads /data/noco.db.
FROM maven:3.9.9-eclipse-temurin-17 AS build
WORKDIR /src
COPY webapp/ ./
# build-frontend after compile, then jar + repackage directly: a full "package"
# would run prepare-frontend again and reset the jar to development mode.
RUN mvn -B -DskipTests -Dvaadin.productionMode=true \
        compile vaadin:build-frontend jar:jar spring-boot:repackage \
 && cp target/noco-webapp-*.jar /app.jar

FROM eclipse-temurin:17-jre
ENV TZ=Europe/Zurich
COPY --from=build /app.jar /app.jar
USER 1000:1000
EXPOSE 8080
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-jar", "/app.jar"]
