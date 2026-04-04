using DataCenterAssetTracker.Data;
using DataCenterAssetTracker.Services;
using Hangfire;
using Hangfire.PostgreSql;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

// Database
var connectionString = builder.Configuration.GetConnectionString("DefaultConnection")
    ?? throw new InvalidOperationException("Connection string 'DefaultConnection' not found.");

builder.Services.AddDbContext<AssetDbContext>(opts =>
    opts.UseNpgsql(connectionString));

// Hangfire (background jobs)
builder.Services.AddHangfire(config =>
    config.UsePostgreSqlStorage(c =>
        c.UseConnectionString(connectionString)));
builder.Services.AddHangfireServer();

// App services
builder.Services.AddScoped<IAssetService, AssetService>();
builder.Services.AddScoped<IValidationService, ValidationService>();

// API
builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(c =>
{
    c.SwaggerDoc("v1", new()
    {
        Title       = "DataCenter Asset Tracker API",
        Version     = "v1",
        Description = "Hardware lifecycle management API for datacenter assets"
    });
    var xmlFile = $"{System.Reflection.Assembly.GetExecutingAssembly().GetName().Name}.xml";
    var xmlPath = Path.Combine(AppContext.BaseDirectory, xmlFile);
    if (File.Exists(xmlPath)) c.IncludeXmlComments(xmlPath);
});

var app = builder.Build();

// Auto-run migrations on startup (skipped for in-memory test provider)
using (var scope = app.Services.CreateScope())
{
    var dbContext = scope.ServiceProvider.GetRequiredService<AssetDbContext>();
    if (dbContext.Database.IsRelational())
        await dbContext.Database.MigrateAsync();
}

app.UseSwagger();
app.UseSwaggerUI();
app.UseHttpsRedirection();
app.MapControllers();
app.MapHangfireDashboard("/hangfire");

app.MapGet("/health", () => Results.Ok(new { Status = "Healthy", Timestamp = DateTime.UtcNow }));

app.Run();

public partial class Program { } // needed for test project
