cmake_minimum_required(VERSION 3.12)
project(verify-find-llama LANGUAGES CXX)
find_package(Llama REQUIRED)
message(STATUS "verify-find-llama: Llama found")
