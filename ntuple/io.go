package ntuple

import (
	"compress/gzip"
	"encoding/gob"
	"os"
	"path/filepath"
)

// Save writes the network to path as gzip'd gob (weights are large and mostly
// zero early in training, so they compress well).
func (n *Network) Save(path string) error {
	if dir := filepath.Dir(path); dir != "" {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return err
		}
	}
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	gz := gzip.NewWriter(f)
	if err := gob.NewEncoder(gz).Encode(n); err != nil {
		return err
	}
	return gz.Close()
}

// Load reads a network written by Save.
func Load(path string) (*Network, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	gz, err := gzip.NewReader(f)
	if err != nil {
		return nil, err
	}
	defer gz.Close()
	var n Network
	if err := gob.NewDecoder(gz).Decode(&n); err != nil {
		return nil, err
	}
	return &n, nil
}
