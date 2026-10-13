"""Benchmark de modelos: los mismos casos, para comparar en este equipo.

No forma parte de la aplicación y no corre con `pytest`: necesita Ollama y
GPU, y tarda. Usa las piezas reales (proveedor, prompts, validadores), porque
si tuviera sus propias copias mediría otra cosa.

    python -m benchmark --model qwen3:8b --model gemma4:e4b
"""
