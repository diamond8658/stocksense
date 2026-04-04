using DataCenterAssetTracker.Data;
using DataCenterAssetTracker.Models;
using Microsoft.EntityFrameworkCore;

namespace DataCenterAssetTracker.Services;

public interface IAssetService
{
    Task<AssetResponse> CreateAsync(CreateAssetRequest request);
    Task<IEnumerable<AssetResponse>> GetAllAsync(AssetStatus? status, AssetType? type, string? location);
    Task<AssetDetailResponse?> GetByIdAsync(Guid id);
    Task<AssetResponse?> UpdateAsync(Guid id, UpdateAssetRequest request);
    Task<AssetResponse?> TransitionStatusAsync(Guid id, TransitionStatusRequest request);
    Task<bool> DeleteAsync(Guid id);
}

public class AssetService(AssetDbContext db) : IAssetService
{
    public async Task<AssetResponse> CreateAsync(CreateAssetRequest req)
    {
        var asset = new Asset
        {
            SerialNumber      = req.SerialNumber,
            Manufacturer      = req.Manufacturer,
            Model             = req.Model,
            Type              = req.Type,
            IpAddress         = req.IpAddress,
            MacAddress        = req.MacAddress,
            DnsHostname       = req.DnsHostname,
            FirmwareVersion   = req.FirmwareVersion,
            DatacenterLocation = req.DatacenterLocation,
            Rack              = req.Rack,
        };

        db.Assets.Add(asset);
        db.AuditLogs.Add(new AuditLog
        {
            AssetId   = asset.Id,
            Action    = "Created",
            Details   = $"Asset registered with serial {asset.SerialNumber}",
            NewStatus = asset.Status
        });

        await db.SaveChangesAsync();
        return asset.ToResponse();
    }

    public async Task<IEnumerable<AssetResponse>> GetAllAsync(
        AssetStatus? status, AssetType? type, string? location)
    {
        var query = db.Assets.AsQueryable();
        if (status is not null) query = query.Where(a => a.Status == status);
        if (type is not null)   query = query.Where(a => a.Type == type);
        if (location is not null) query = query.Where(a => a.DatacenterLocation == location);

        return (await query.ToListAsync()).Select(a => a.ToResponse());
    }

    public async Task<AssetDetailResponse?> GetByIdAsync(Guid id)
    {
        var asset = await db.Assets
            .Include(a => a.AuditLogs)
            .Include(a => a.ValidationResults)
            .FirstOrDefaultAsync(a => a.Id == id);

        return asset?.ToDetailResponse();
    }

    public async Task<AssetResponse?> UpdateAsync(Guid id, UpdateAssetRequest req)
    {
        var asset = await db.Assets.FindAsync(id);
        if (asset is null) return null;

        if (req.Manufacturer is not null) asset.Manufacturer = req.Manufacturer;
        if (req.Model is not null)        asset.Model = req.Model;
        if (req.IpAddress is not null)    asset.IpAddress = req.IpAddress;
        if (req.MacAddress is not null)   asset.MacAddress = req.MacAddress;
        if (req.DnsHostname is not null)  asset.DnsHostname = req.DnsHostname;
        if (req.FirmwareVersion is not null) asset.FirmwareVersion = req.FirmwareVersion;
        if (req.DatacenterLocation is not null) asset.DatacenterLocation = req.DatacenterLocation;
        if (req.Rack is not null)         asset.Rack = req.Rack;

        asset.UpdatedAt = DateTime.UtcNow;

        db.AuditLogs.Add(new AuditLog
        {
            AssetId = asset.Id,
            Action  = "Updated",
            Details = "Asset metadata updated"
        });

        await db.SaveChangesAsync();
        return asset.ToResponse();
    }

    public async Task<AssetResponse?> TransitionStatusAsync(Guid id, TransitionStatusRequest req)
    {
        var asset = await db.Assets.FindAsync(id);
        if (asset is null) return null;

        if (!AssetLifecycle.CanTransition(asset.Status, req.NewStatus))
            throw new InvalidOperationException(
                $"Cannot transition from {asset.Status} to {req.NewStatus}.");

        var previous = asset.Status;
        asset.Status    = req.NewStatus;
        asset.UpdatedAt = DateTime.UtcNow;

        db.AuditLogs.Add(new AuditLog
        {
            AssetId        = asset.Id,
            Action         = "StatusChanged",
            Details        = req.Reason,
            PreviousStatus = previous,
            NewStatus      = req.NewStatus
        });

        await db.SaveChangesAsync();
        return asset.ToResponse();
    }

    public async Task<bool> DeleteAsync(Guid id)
    {
        var asset = await db.Assets.FindAsync(id);
        if (asset is null) return false;

        db.Assets.Remove(asset);
        await db.SaveChangesAsync();
        return true;
    }
}

// Mapping helpers
file static class AssetExtensions
{
    public static AssetResponse ToResponse(this Asset a) => new(
        a.Id, a.SerialNumber, a.Manufacturer, a.Model, a.Type,
        a.IpAddress, a.MacAddress, a.DnsHostname, a.FirmwareVersion,
        a.DatacenterLocation, a.Rack, a.Status, a.CreatedAt, a.UpdatedAt);

    public static AssetDetailResponse ToDetailResponse(this Asset a) => new(
        a.Id, a.SerialNumber, a.Manufacturer, a.Model, a.Type,
        a.IpAddress, a.MacAddress, a.DnsHostname, a.FirmwareVersion,
        a.DatacenterLocation, a.Rack, a.Status, a.CreatedAt, a.UpdatedAt,
        a.AuditLogs.Select(l => new AuditLogResponse(
            l.Id, l.Action, l.Details, l.PreviousStatus, l.NewStatus, l.Timestamp)),
        a.ValidationResults.Select(v => new ValidationResultResponse(
            v.Id, v.CheckName, v.Passed, v.Details, v.RunAt)));
}
