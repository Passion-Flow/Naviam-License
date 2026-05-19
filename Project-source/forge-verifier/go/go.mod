module github.com/your-co/forge-verifier-go

go 1.23

require github.com/tjfoc/gmsm v1.4.1

// Note: Go 1.23+ required because of the macOS 14+ linker change
// (`missing LC_UUID load command` blocks earlier Go's `go test` binaries).
