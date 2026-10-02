//! The bitstream the simulation's variant decoder reads: fields packed
//! most-significant bit first, back to back with no alignment, the stream
//! consumed through a big-endian 64-bit cache (HaloSimulation CU4 `0x3f8a00`
//! builds the reader). Writing MSB-first into bytes gives the same bit order.

use crate::Error;

/// Accumulates fields MSB-first.
#[derive(Debug, Default, Clone)]
pub struct BitWriter {
    bytes: Vec<u8>,
    /// Bits used in the last byte (0..8; 0 means the last byte is full or
    /// there is none).
    used: u32,
}

impl BitWriter {
    pub fn new() -> Self {
        Self::default()
    }

    /// Bits written so far.
    pub fn len(&self) -> usize {
        if self.used == 0 {
            self.bytes.len() * 8
        } else {
            (self.bytes.len() - 1) * 8 + self.used as usize
        }
    }

    pub fn is_empty(&self) -> bool {
        self.bytes.is_empty()
    }

    /// Write the low `bits` bits of `value`, most significant first.
    pub fn write(&mut self, value: u64, bits: u32) -> Result<(), Error> {
        if bits < 64 && value >> bits != 0 {
            return Err(Error::TooWide {
                value: value as i64,
                bits,
            });
        }
        for i in (0..bits).rev() {
            self.bit((value >> i) & 1 == 1);
        }
        Ok(())
    }

    /// A signed value in `bits`-bit two's complement.
    pub fn write_signed(&mut self, value: i64, bits: u32) -> Result<(), Error> {
        let min = -(1i64 << (bits - 1));
        let max = (1i64 << (bits - 1)) - 1;
        if value < min || value > max {
            return Err(Error::TooWide { value, bits });
        }
        let mask = if bits == 64 {
            u64::MAX
        } else {
            (1u64 << bits) - 1
        };
        self.write(value as u64 & mask, bits)
    }

    pub fn bool(&mut self, v: bool) {
        self.bit(v);
    }

    fn bit(&mut self, v: bool) {
        if self.used == 0 {
            self.bytes.push(0);
        }
        if v {
            *self.bytes.last_mut().unwrap() |= 0x80 >> self.used;
        }
        self.used = (self.used + 1) % 8;
    }

    /// The bytes, the last one zero-padded.
    pub fn finish(self) -> Vec<u8> {
        self.bytes
    }
}

/// Reads fields MSB-first, as the simulation's decoder does.
#[derive(Debug, Clone)]
pub struct BitReader<'a> {
    bytes: &'a [u8],
    at: usize,
}

impl<'a> BitReader<'a> {
    pub fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, at: 0 }
    }

    /// The bit position.
    pub fn position(&self) -> usize {
        self.at
    }

    pub fn remaining(&self) -> usize {
        self.bytes.len() * 8 - self.at
    }

    pub fn read(&mut self, bits: u32) -> Result<u64, Error> {
        if (bits as usize) > self.remaining() {
            return Err(Error::Truncated {
                at: self.at,
                want: bits,
            });
        }
        let mut v = 0u64;
        for _ in 0..bits {
            let byte = self.bytes[self.at / 8];
            let bit = (byte >> (7 - self.at % 8)) & 1;
            v = (v << 1) | bit as u64;
            self.at += 1;
        }
        Ok(v)
    }

    pub fn read_signed(&mut self, bits: u32) -> Result<i64, Error> {
        let v = self.read(bits)?;
        let sign = 1u64 << (bits - 1);
        Ok(if v & sign != 0 {
            v as i64 - (1i64 << bits)
        } else {
            v as i64
        })
    }

    pub fn bool(&mut self) -> Result<bool, Error> {
        Ok(self.read(1)? == 1)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fields_pack_msb_first_without_alignment() {
        let mut w = BitWriter::new();
        w.write(0b101, 3).unwrap();
        w.write(0x6b, 8).unwrap();
        w.bool(true);
        w.write_signed(-2, 5).unwrap();
        assert_eq!(w.len(), 17);
        let bytes = w.finish();
        // 101 01101011 1 11110 -> 1010 1101 | 0111 1111 | 0(pad)...
        assert_eq!(bytes, vec![0b1010_1101, 0b0111_1111, 0b0000_0000]);
        let mut r = BitReader::new(&bytes);
        assert_eq!(r.read(3).unwrap(), 0b101);
        assert_eq!(r.read(8).unwrap(), 0x6b);
        assert!(r.bool().unwrap());
        assert_eq!(r.read_signed(5).unwrap(), -2);
    }

    #[test]
    fn a_value_too_wide_is_refused() {
        let mut w = BitWriter::new();
        assert!(w.write(8, 3).is_err());
        assert!(w.write_signed(16, 5).is_err());
        assert!(w.write_signed(-17, 5).is_err());
    }

    #[test]
    fn reading_past_the_end_is_an_error() {
        let mut r = BitReader::new(&[0xff]);
        assert_eq!(r.read(8).unwrap(), 0xff);
        assert!(r.read(1).is_err());
    }
}
