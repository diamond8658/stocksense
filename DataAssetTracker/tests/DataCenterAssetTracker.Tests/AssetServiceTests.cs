using DataCenterAssetTracker.Data;
using DataCenterAssetTracker.Models;
using DataCenterAssetTracker.Services;
using FluentAssertions;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace DataCenterAssetTracker.Tests;

public class AssetLifecycleTests
{
    [Theory]
    [InlineData(AssetStatus.Pending,    AssetStatus.Validating, true)]
    [InlineData(AssetStatus.Pending,    AssetStatus.Retired,    true)]
    [InlineData(AssetStatus.Pending,    AssetStatus.Deployed,   false)]
    [InlineData(AssetStatus.Validating, AssetStatus.Approved,   true)]
    [InlineData(AssetStatus.Validating, AssetStatus.Pending,    true)]
    [InlineData(AssetStatus.Approved,   AssetStatus.Deployed,   true)]
    [InlineData(AssetStatus.Approved,   AssetStatus.Pending,    false)]
    [InlineData(AssetStatus.Deployed,   AssetStatus.Retired,    true)]
    [InlineData(AssetStatus.Deployed,   AssetStatus.Pending,    false)]
    [InlineData(AssetStatus.Retired,    AssetStatus.Pending,    false)]
    public void CanTransition_ReturnsExpected(AssetStatus from, AssetStatus to, bool expected)
    {
        AssetLifecycle.CanTransition(from, to).Should().Be(expected);
    }
}

public class AssetServiceTests
{
    private static AssetDbContext CreateDb()
    {
        var options = new DbContextOptionsBuilder<AssetDbContext>()
            .UseInMemoryDatabase(Guid.NewGuid().ToString())
            .Options;
        return new AssetDbContext(options);
    }

    private static CreateAssetRequest SampleRequest(string serial = "SN-001", string mac = "AA:BB:CC:DD:EE:FF") => new(
        SerialNumber:       serial,
        Manufacturer:       "Dell",
        Model:              "PowerEdge R750",
        Type:               AssetType.Server,
        IpAddress:          "10.0.0.1",
        MacAddress:         mac,
        DnsHostname:        "rack1-server1.dc.local",
        FirmwareVersion:    "2.1.0",
        DatacenterLocation: "West US 2",
        Rack:               "A1"
    );

    [Fact]
    public async Task CreateAsync_CreatesAssetWithPendingStatus()
    {
        using var db     = CreateDb();
        var service      = new AssetService(db);
        var result       = await service.CreateAsync(SampleRequest());

        result.Status.Should().Be(AssetStatus.Pending);
        result.SerialNumber.Should().Be("SN-001");
    }

    [Fact]
    public async Task CreateAsync_WritesAuditLog()
    {
        using var db = CreateDb();
        var service  = new AssetService(db);
        var result   = await service.CreateAsync(SampleRequest());

        var logs = db.AuditLogs.Where(l => l.AssetId == result.Id).ToList();
        logs.Should().HaveCount(1);
        logs[0].Action.Should().Be("Created");
    }

    [Fact]
    public async Task TransitionStatusAsync_ValidTransition_Succeeds()
    {
        using var db = CreateDb();
        var service  = new AssetService(db);
        var asset    = await service.CreateAsync(SampleRequest());

        var result = await service.TransitionStatusAsync(
            asset.Id, new TransitionStatusRequest(AssetStatus.Validating, "Starting validation"));

        result!.Status.Should().Be(AssetStatus.Validating);
    }

    [Fact]
    public async Task TransitionStatusAsync_InvalidTransition_Throws()
    {
        using var db = CreateDb();
        var service  = new AssetService(db);
        var asset    = await service.CreateAsync(SampleRequest());

        var act = async () => await service.TransitionStatusAsync(
            asset.Id, new TransitionStatusRequest(AssetStatus.Deployed, "Invalid jump"));

        await act.Should().ThrowAsync<InvalidOperationException>();
    }

    [Fact]
    public async Task UpdateAsync_UpdatesMetadata()
    {
        using var db = CreateDb();
        var service  = new AssetService(db);
        var asset    = await service.CreateAsync(SampleRequest());

        var updated = await service.UpdateAsync(
            asset.Id, new UpdateAssetRequest(null, null, "10.0.0.2", null, null, "2.2.0", null, null));

        updated!.IpAddress.Should().Be("10.0.0.2");
        updated.FirmwareVersion.Should().Be("2.2.0");
    }

    [Fact]
    public async Task DeleteAsync_RemovesAsset()
    {
        using var db = CreateDb();
        var service  = new AssetService(db);
        var asset    = await service.CreateAsync(SampleRequest());

        var deleted = await service.DeleteAsync(asset.Id);
        deleted.Should().BeTrue();

        var found = await service.GetByIdAsync(asset.Id);
        found.Should().BeNull();
    }

    [Fact]
    public async Task GetAllAsync_FiltersCorrectly()
    {
        using var db = CreateDb();
        var service  = new AssetService(db);
        await service.CreateAsync(SampleRequest("SN-001", "AA:BB:CC:DD:EE:01"));
        await service.CreateAsync(SampleRequest("SN-002", "AA:BB:CC:DD:EE:02") with { DatacenterLocation = "East US" });

        var westAssets = await service.GetAllAsync(null, null, "West US 2");
        westAssets.Should().HaveCount(1);
        westAssets.First().SerialNumber.Should().Be("SN-001");
    }
}
