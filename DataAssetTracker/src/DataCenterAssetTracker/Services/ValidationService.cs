using System.Net.NetworkInformation;
using DataCenterAssetTracker.Data;
using DataCenterAssetTracker.Models;
using Microsoft.EntityFrameworkCore;

namespace DataCenterAssetTracker.Services;

public interface IValidationService
{
    Task RunValidationAsync(Guid assetId);
}

public class ValidationService(AssetDbContext db, IConfiguration config) : IValidationService
{
    // Known-good firmware versions per asset type — configurable via appsettings
    private Dictionary<AssetType, string[]> GetApprovedFirmware() =>
        config.GetSection("ApprovedFirmware").Get<Dictionary<AssetType, string[]>>()
        ?? new Dictionary<AssetType, string[]>();

    public async Task RunValidationAsync(Guid assetId)
    {
        var asset = await db.Assets.FindAsync(assetId);
        if (asset is null) return;

        var results = new List<ValidationResult>();

        // 1. Ping check
        results.Add(await RunPingCheckAsync(asset));

        // 2. Firmware check
        results.Add(RunFirmwareCheck(asset));

        // 3. Duplicate serial/MAC check
        results.Add(await RunDuplicateCheckAsync(asset));

        db.ValidationResults.AddRange(results);

        // Determine overall pass/fail and auto-transition
        var allPassed = results.All(r => r.Passed);
        var previous  = asset.Status;

        asset.Status    = allPassed ? AssetStatus.Approved : AssetStatus.Pending;
        asset.UpdatedAt = DateTime.UtcNow;

        db.AuditLogs.Add(new AuditLog
        {
            AssetId        = assetId,
            Action         = "ValidationComplete",
            Details        = allPassed ? "All checks passed" : "One or more checks failed",
            PreviousStatus = previous,
            NewStatus      = asset.Status
        });

        await db.SaveChangesAsync();
    }

    private async Task<ValidationResult> RunPingCheckAsync(Asset asset)
    {
        if (string.IsNullOrWhiteSpace(asset.IpAddress))
            return Fail(asset.Id, "PingCheck", "No IP address registered");

        try
        {
            using var ping   = new Ping();
            var reply        = await ping.SendPingAsync(asset.IpAddress, timeout: 3000);
            var passed       = reply.Status == IPStatus.Success;
            return new ValidationResult
            {
                AssetId   = asset.Id,
                CheckName = "PingCheck",
                Passed    = passed,
                Details   = passed
                    ? $"Device responded in {reply.RoundtripTime}ms"
                    : $"Ping failed: {reply.Status}"
            };
        }
        catch (Exception ex)
        {
            return Fail(asset.Id, "PingCheck", $"Ping error: {ex.Message}");
        }
    }

    private ValidationResult RunFirmwareCheck(Asset asset)
    {
        if (string.IsNullOrWhiteSpace(asset.FirmwareVersion))
            return Fail(asset.Id, "FirmwareCheck", "No firmware version registered");

        var approved = GetApprovedFirmware();
        if (!approved.TryGetValue(asset.Type, out var versions))
            return new ValidationResult
            {
                AssetId   = asset.Id,
                CheckName = "FirmwareCheck",
                Passed    = true,
                Details   = $"No approved firmware list configured for {asset.Type} — skipped"
            };

        var passed = versions.Contains(asset.FirmwareVersion, StringComparer.OrdinalIgnoreCase);
        return new ValidationResult
        {
            AssetId   = asset.Id,
            CheckName = "FirmwareCheck",
            Passed    = passed,
            Details   = passed
                ? $"Firmware {asset.FirmwareVersion} is approved"
                : $"Firmware {asset.FirmwareVersion} is not in the approved list: [{string.Join(", ", versions)}]"
        };
    }

    private async Task<ValidationResult> RunDuplicateCheckAsync(Asset asset)
    {
        var duplicateSerial = await db.Assets
            .AnyAsync(a => a.SerialNumber == asset.SerialNumber && a.Id != asset.Id);

        var duplicateMac = !string.IsNullOrWhiteSpace(asset.MacAddress) &&
            await db.Assets
                .AnyAsync(a => a.MacAddress == asset.MacAddress && a.Id != asset.Id);

        var passed  = !duplicateSerial && !duplicateMac;
        var messages = new List<string>();
        if (duplicateSerial) messages.Add("Duplicate serial number detected");
        if (duplicateMac)    messages.Add("Duplicate MAC address detected");
        var details = passed ? "No duplicates found" : string.Join("; ", messages);

        return new ValidationResult
        {
            AssetId   = asset.Id,
            CheckName = "DuplicateCheck",
            Passed    = passed,
            Details   = details
        };
    }

    private static ValidationResult Fail(Guid assetId, string check, string details) =>
        new() { AssetId = assetId, CheckName = check, Passed = false, Details = details };
}
