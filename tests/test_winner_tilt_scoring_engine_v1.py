from winner_tilt import scoring as e

def test_percentile_direction():
    vals=[1,2,3,4,5]
    assert e.percentile(vals,5) > e.percentile(vals,1)
    assert (100-e.percentile(vals,1)) > (100-e.percentile(vals,5))

def test_ties_are_midrank():
    assert e.percentile([1,2,2,3],2)==50.0

def test_quantile_bounds():
    vals=[0,1,2,100]
    assert e.quantile(vals,0.05) >= 0
    assert e.quantile(vals,0.95) <= 100

def test_stage_modules():
    assert e.stage_ok('ALL','EMG')
    assert e.stage_ok('GRW_MAT','GRW')
    assert not e.stage_ok('GRW_MAT','EMG')
    assert e.stage_ok('EMG','EMG')
    assert not e.stage_ok('MAT','GRW')

if __name__=='__main__':
    for name,obj in sorted(globals().items()):
        if name.startswith('test_'):
            obj(); print('PASS',name)
