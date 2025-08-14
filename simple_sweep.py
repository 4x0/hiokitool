#!/usr/bin/env python3
"""
Simple IO sweep example for hiokitool
Cycles through IO outputs 0-7 and takes measurements
"""

def sequence(api):
    """Sweep through IO configurations"""
    
    api.log("Starting simple IO sweep")
    
    # Set measurement parameters
    api.set_range('10V')
    api.set_speed('MED')
    
    # Sweep through IO values 0-7
    for io_value in range(8):
        api.log(f"Testing IO configuration: {io_value} (binary: {io_value:03b})")
        
        # Set IO output
        api.set_io(io_value)
        
        # Small delay for settling
        api.wait(0.2)
        
        # Take 5 measurements
        measurements = api.measure(5, delay_ms=50)
        
        # Calculate and display average
        valid = [m for m in measurements if m is not None]
        if valid:
            avg = sum(valid) / len(valid)
            api.log(f"  Average: {avg:.3f}V from {len(valid)} samples")
        else:
            api.log("  No valid measurements")
    
    # Display summary
    stats = api.get_statistics()
    api.log(f"\nSweep complete: {stats['count']} total measurements")
    api.log(f"Range: {stats['min']:.3f}V to {stats['max']:.3f}V")
    
    return api.results