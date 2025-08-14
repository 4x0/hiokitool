#!/usr/bin/env python3
"""
Example test sequence for hiokitool
Demonstrates the scripting API capabilities
"""

def sequence(api):
    """Main sequence function called by hiokitool"""
    
    # Set test metadata
    api.set_metadata('test_name', 'Multi-range characterization')
    api.set_metadata('operator', 'Automated')
    api.set_metadata('date', api.get_metadata('date'))  # Will be None if not set
    
    api.log("Starting multi-range characterization test")
    
    # Test configuration matrix
    test_matrix = [
        # (io_output, voltage_range, speed, samples, description)
        (0b00000000001, '10V', 'SLOW', 10, 'Channel A, 10V range, slow'),
        (0b00000000001, '10V', 'FAST', 10, 'Channel A, 10V range, fast'),
        (0b00000000010, '10V', 'SLOW', 10, 'Channel B, 10V range, slow'),
        (0b00000000010, '100V', 'SLOW', 5, 'Channel B, 100V range, slow'),
        (0b00000000100, '100V', 'MED', 10, 'Channel C, 100V range, medium'),
        (0b00000001000, '1000V', 'SLOW', 5, 'Channel D, 1000V range, slow'),
    ]
    
    # Execute test matrix
    for io, vrange, speed, samples, description in test_matrix:
        api.log(f"\n--- Test: {description} ---")
        
        # Configure measurement
        api.set_io(io)
        api.set_range(vrange)
        api.set_speed(speed)
        
        # Wait for settling
        api.wait(0.5)
        
        # Take measurements
        results = api.measure(samples, delay_ms=100)
        
        # Check for valid results
        valid_results = [r for r in results if r is not None]
        if not valid_results:
            api.log(f"WARNING: No valid measurements for {description}")
            continue
        
        # Calculate statistics
        mean_val = sum(valid_results) / len(valid_results)
        max_val = max(valid_results)
        min_val = min(valid_results)
        
        # Display results
        api.log(f"Results: Mean={mean_val:.4f}V, Max={max_val:.4f}V, Min={min_val:.4f}V")
        
        # Check for over-range condition
        if vrange == '10V' and max_val > 9.5:
            api.log("Near over-range detected, switching to higher range")
            api.set_range('100V')
            # Re-measure with higher range
            results_retry = api.measure(5, delay_ms=100)
            valid_retry = [r for r in results_retry if r is not None]
            if valid_retry:
                api.log(f"Retry at 100V: Mean={sum(valid_retry)/len(valid_retry):.4f}V")
        
        # Store metadata for this measurement set
        api.set_metadata(f'test_{io:011b}_{vrange}', {
            'mean': mean_val,
            'max': max_val,
            'min': min_val,
            'samples': len(valid_results)
        })
    
    # Final statistics
    api.log("\n=== Test Complete ===")
    stats = api.get_statistics()
    api.log(f"Total measurements: {stats['count']}")
    api.log(f"Overall mean: {stats['mean']:.4f}V")
    api.log(f"Overall range: {stats['min']:.4f}V to {stats['max']:.4f}V")
    
    # Save results
    filename = api.save_results('characterization_results.csv')
    api.log(f"Results saved to: {filename}")
    
    return api.results


# Alternative entry point
def main(api):
    """Alternative entry point for the script"""
    return sequence(api)