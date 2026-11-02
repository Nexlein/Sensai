FROM maven:3.9-eclipse-temurin-25@sha256:93b8a14ea2f412782e4e842651273b4d903e35cc496284f178fbbe2d67d00976 AS build

WORKDIR /app

COPY pom.xml .
RUN mvn -q -B dependency:go-offline

COPY src ./src
RUN mvn -q -B -o package

FROM eclipse-temurin:25-jre@sha256:fcd7fd7b387f94bb2ac461478a7436ad8e349924c374ea8313919624dceae636

ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75 -XX:+ExitOnOutOfMemoryError"

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=build /app/target/worker-jar-with-dependencies.jar ./worker.jar

USER 10001

EXPOSE 80

CMD ["java", "-jar", "worker.jar"]
