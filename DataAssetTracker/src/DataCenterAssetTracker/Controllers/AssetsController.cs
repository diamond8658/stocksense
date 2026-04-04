using DataCenterAssetTracker.Models;
using DataCenterAssetTracker.Services;
using Hangfire;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DataCenterAssetTracker.Controllers;

[ApiController]
[Route("api/[controller]")]
public class AssetsController(IAssetService assetService, IBackgroundJobClient jobs) : ControllerBase
{
    /// <summary>Register a new hardware asset.</summary>
    [HttpPost]
    [ProducesResponseType(typeof(AssetResponse), StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<IActionResult> Create([FromBody] CreateAssetRequest request)
    {
        try
        {
            var asset = await assetService.CreateAsync(request);
            return CreatedAtAction(nameof(GetById), new { id = asset.Id }, asset);
        }
        catch (DbUpdateException)
        {
            return Conflict("An asset with this serial number or MAC address already exists.");
        }
    }

    /// <summary>List all assets with optional filters.</summary>
    [HttpGet]
    [ProducesResponseType(typeof(IEnumerable<AssetResponse>), StatusCodes.Status200OK)]
    public async Task<IActionResult> GetAll(
        [FromQuery] AssetStatus? status,
        [FromQuery] AssetType? type,
        [FromQuery] string? location)
    {
        var assets = await assetService.GetAllAsync(status, type, location);
        return Ok(assets);
    }

    /// <summary>Get full details for a single asset including audit log and validation results.</summary>
    [HttpGet("{id:guid}")]
    [ProducesResponseType(typeof(AssetDetailResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> GetById(Guid id)
    {
        var asset = await assetService.GetByIdAsync(id);
        return asset is null ? NotFound() : Ok(asset);
    }

    /// <summary>Update asset metadata.</summary>
    [HttpPatch("{id:guid}")]
    [ProducesResponseType(typeof(AssetResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Update(Guid id, [FromBody] UpdateAssetRequest request)
    {
        var asset = await assetService.UpdateAsync(id, request);
        return asset is null ? NotFound() : Ok(asset);
    }

    /// <summary>Transition an asset to a new lifecycle status.</summary>
    [HttpPost("{id:guid}/status")]
    [ProducesResponseType(typeof(AssetResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> TransitionStatus(Guid id, [FromBody] TransitionStatusRequest request)
    {
        try
        {
            var asset = await assetService.TransitionStatusAsync(id, request);
            if (asset is null) return NotFound();

            // Trigger background validation when asset enters Validating state
            if (request.NewStatus == AssetStatus.Validating)
                jobs.Enqueue<IValidationService>(svc => svc.RunValidationAsync(id));

            return Ok(asset);
        }
        catch (InvalidOperationException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    /// <summary>Retire and remove an asset.</summary>
    [HttpDelete("{id:guid}")]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Delete(Guid id)
    {
        var deleted = await assetService.DeleteAsync(id);
        return deleted ? NoContent() : NotFound();
    }
}
