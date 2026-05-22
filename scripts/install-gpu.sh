#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

UV="${UV:-$HOME/.local/bin/uv}"
if [[ ! -x "$UV" ]]; then
  UV="uv"
fi

if ! command -v nvcc >/dev/null 2>&1 && [[ -x /opt/cuda/bin/nvcc ]]; then
  export PATH="/opt/cuda/bin:$PATH"
fi

if ! command -v nvcc >/dev/null 2>&1; then
  echo "nvcc was not found on PATH. Install the CUDA toolkit or add its bin directory to PATH." >&2
  exit 1
fi

if [[ -x /usr/bin/gcc-15 && -x /usr/bin/g++-15 ]]; then
  export CC="${CC:-/usr/bin/gcc-15}"
  export CXX="${CXX:-/usr/bin/g++-15}"
  export CUDAHOSTCXX="${CUDAHOSTCXX:-/usr/bin/g++-15}"
  host_compiler_args="-DCMAKE_C_COMPILER=$CC -DCMAKE_CXX_COMPILER=$CXX -DCMAKE_CUDA_HOST_COMPILER=$CUDAHOSTCXX"
else
  host_compiler_args=""
fi

export CMAKE_ARGS="${CMAKE_ARGS:--DGGML_CUDA=on $host_compiler_args}"
export FORCE_CMAKE="${FORCE_CMAKE:-1}"

"$UV" sync --reinstall-package llama-cpp-python

"$UV" run python - <<'PY'
from llama_cpp import llama_cpp as lc

if not lc.llama_supports_gpu_offload():
    raise SystemExit(
        "llama-cpp-python installed, but GPU offload is still unavailable. "
        "Check that nvcc is on PATH and the CUDA source build completed successfully."
    )

print("llama-cpp-python GPU offload is available.")
PY
