"""Setup for J.A.R.V.I.S — Supreme Brainiac Personal Agent."""
from setuptools import setup, find_packages

setup(
    name="jarvis-supreme-agent",
    version="24.0.0",
    author="Amjad Mobarsham",
    author_email="amjad@example.com",
    description="J.A.R.V.I.S — Supreme Brainiac Personal Agent with Humanoid Robot Brain",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/amjad2161/agency-agents",
    packages=find_packages(where="runtime"),
    package_dir={"": "runtime"},
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0",
    ],
    extras_require={
        "llm": ["anthropic>=0.30"],
        "voice": ["openai-whisper", "edge-tts", "gTTS", "pyttsx3"],
        "vision": ["ultralytics>=8.0", "opencv-python>=4.8", "mediapipe"],
        "robotics": ["pybullet", "mujoco", "numpy"],
        "dashboard": ["flask>=2.0", "flask-socketio"],
        "memory": ["sentence-transformers>=2.0", "scikit-learn"],
        "dev": ["pytest>=7.0", "black", "flake8", "mypy"],
        "all": [
            "anthropic>=0.30",
            "openai-whisper", "edge-tts", "gTTS", "pyttsx3",
            "ultralytics>=8.0", "opencv-python>=4.8", "mediapipe",
            "pybullet", "mujoco", "numpy",
            "flask>=2.0", "flask-socketio",
            "sentence-transformers>=2.0", "scikit-learn",
            "watchdog", "httpx", "tomli",
        ],
    },
    entry_points={
        "console_scripts": [
            "agency=agency.cli:cli",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
