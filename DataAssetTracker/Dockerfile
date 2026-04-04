FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS base
WORKDIR /app
EXPOSE 8080

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY ["src/DataCenterAssetTracker/DataCenterAssetTracker.csproj", "src/DataCenterAssetTracker/"]
RUN dotnet restore "src/DataCenterAssetTracker/DataCenterAssetTracker.csproj"
COPY . .
WORKDIR "/src/src/DataCenterAssetTracker"
RUN dotnet build "DataCenterAssetTracker.csproj" -c Release -o /app/build

FROM build AS publish
RUN dotnet publish "DataCenterAssetTracker.csproj" -c Release -o /app/publish /p:UseAppHost=false

FROM base AS final
WORKDIR /app
COPY --from=publish /app/publish .
ENTRYPOINT ["dotnet", "DataCenterAssetTracker.dll"]
