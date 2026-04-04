namespace DataCenterAssetTracker.Models;

// --- Requests ---

public record CreateAssetRequest(
    string SerialNumber,
    string Manufacturer,
    string Model,
    AssetType Type,
    string? IpAddress,
    string? MacAddress,
    string? DnsHostname,
    string? FirmwareVersion,
    string? DatacenterLocation,
    string? Rack
);

public record UpdateAssetRequest(
    string? Manufacturer,
    string? Model,
    string? IpAddress,
    string? MacAddress,
    string? DnsHostname,
    string? FirmwareVersion,
    string? DatacenterLocation,
    string? Rack
);

public record TransitionStatusRequest(
    AssetStatus NewStatus,
    string Reason
);

// --- Responses ---

public record AssetResponse(
    Guid Id,
    string SerialNumber,
    string Manufacturer,
    string Model,
    AssetType Type,
    string? IpAddress,
    string? MacAddress,
    string? DnsHostname,
    string? FirmwareVersion,
    string? DatacenterLocation,
    string? Rack,
    AssetStatus Status,
    DateTime CreatedAt,
    DateTime UpdatedAt
);

public record AssetDetailResponse(
    Guid Id,
    string SerialNumber,
    string Manufacturer,
    string Model,
    AssetType Type,
    string? IpAddress,
    string? MacAddress,
    string? DnsHostname,
    string? FirmwareVersion,
    string? DatacenterLocation,
    string? Rack,
    AssetStatus Status,
    DateTime CreatedAt,
    DateTime UpdatedAt,
    IEnumerable<AuditLogResponse> AuditLogs,
    IEnumerable<ValidationResultResponse> ValidationResults
);

public record AuditLogResponse(
    Guid Id,
    string Action,
    string Details,
    AssetStatus? PreviousStatus,
    AssetStatus? NewStatus,
    DateTime Timestamp
);

public record ValidationResultResponse(
    Guid Id,
    string CheckName,
    bool Passed,
    string? Details,
    DateTime RunAt
);
