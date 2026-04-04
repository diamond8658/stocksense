namespace DataCenterAssetTracker.Models;

public enum AssetType
{
    Server,
    CPU,
    Memory,
    Storage,
    NetworkInterface,
    Other
}

public enum AssetStatus
{
    Pending,
    Validating,
    Approved,
    Deployed,
    Retired
}

public class Asset
{
    public Guid Id { get; set; } = Guid.NewGuid();

    // Identity
    public required string SerialNumber { get; set; }
    public required string Manufacturer { get; set; }
    public required string Model { get; set; }
    public AssetType Type { get; set; }

    // Network
    public string? IpAddress { get; set; }
    public string? MacAddress { get; set; }
    public string? DnsHostname { get; set; }

    // Firmware
    public string? FirmwareVersion { get; set; }

    // Location
    public string? DatacenterLocation { get; set; }
    public string? Rack { get; set; }

    // Lifecycle
    public AssetStatus Status { get; set; } = AssetStatus.Pending;
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;

    // Navigation
    public ICollection<AuditLog> AuditLogs { get; set; } = [];
    public ICollection<ValidationResult> ValidationResults { get; set; } = [];
}

public class AuditLog
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid AssetId { get; set; }
    public Asset Asset { get; set; } = null!;
    public required string Action { get; set; }
    public required string Details { get; set; }
    public AssetStatus? PreviousStatus { get; set; }
    public AssetStatus? NewStatus { get; set; }
    public DateTime Timestamp { get; set; } = DateTime.UtcNow;
}

public class ValidationResult
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid AssetId { get; set; }
    public Asset Asset { get; set; } = null!;
    public required string CheckName { get; set; }
    public bool Passed { get; set; }
    public string? Details { get; set; }
    public DateTime RunAt { get; set; } = DateTime.UtcNow;
}

// Valid lifecycle transitions
public static class AssetLifecycle
{
    private static readonly Dictionary<AssetStatus, AssetStatus[]> _validTransitions = new()
    {
        [AssetStatus.Pending]    = [AssetStatus.Validating, AssetStatus.Retired],
        [AssetStatus.Validating] = [AssetStatus.Approved, AssetStatus.Pending, AssetStatus.Retired],
        [AssetStatus.Approved]   = [AssetStatus.Deployed, AssetStatus.Retired],
        [AssetStatus.Deployed]   = [AssetStatus.Retired],
        [AssetStatus.Retired]    = []
    };

    public static bool CanTransition(AssetStatus from, AssetStatus to) =>
        _validTransitions.TryGetValue(from, out var allowed) && allowed.Contains(to);
}
