using DataCenterAssetTracker.Models;
using Microsoft.EntityFrameworkCore;

namespace DataCenterAssetTracker.Data;

public class AssetDbContext(DbContextOptions<AssetDbContext> options) : DbContext(options)
{
    public DbSet<Asset> Assets => Set<Asset>();
    public DbSet<AuditLog> AuditLogs => Set<AuditLog>();
    public DbSet<ValidationResult> ValidationResults => Set<ValidationResult>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Asset>(e =>
        {
            e.HasKey(a => a.Id);
            e.HasIndex(a => a.SerialNumber).IsUnique();
            e.HasIndex(a => a.MacAddress).IsUnique().HasFilter("\"MacAddress\" IS NOT NULL");
            e.Property(a => a.Status).HasConversion<string>();
            e.Property(a => a.Type).HasConversion<string>();
        });

        modelBuilder.Entity<AuditLog>(e =>
        {
            e.HasKey(a => a.Id);
            e.Property(a => a.PreviousStatus).HasConversion<string>();
            e.Property(a => a.NewStatus).HasConversion<string>();
            e.HasOne(a => a.Asset)
             .WithMany(a => a.AuditLogs)
             .HasForeignKey(a => a.AssetId)
             .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<ValidationResult>(e =>
        {
            e.HasKey(v => v.Id);
            e.HasOne(v => v.Asset)
             .WithMany(a => a.ValidationResults)
             .HasForeignKey(v => v.AssetId)
             .OnDelete(DeleteBehavior.Cascade);
        });
    }
}
