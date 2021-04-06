from shadowproxy2.buffer import Buffer


def test_buffer():
    buf = Buffer(20)
    buf.push(b"haha")
    assert buf.data_size == 4
    assert len(buf) == 4
    assert buf.available_size == 16
