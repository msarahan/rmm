/*
 * Copyright (c) 2023, NVIDIA CORPORATION.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "mr_ref_test.hpp"

#include <rmm/mr/device/per_device_resource.hpp>

#include <cuda/memory_resource>

#include <gtest/gtest.h>

namespace rmm::test {
namespace {

INSTANTIATE_TEST_SUITE_P(ResourceTests,
                         mr_ref_test,
                         ::testing::Values(mr_factory{"CUDA", &make_cuda},
#ifdef RMM_CUDA_MALLOC_ASYNC_SUPPORT
                                           mr_factory{"CUDA_Async", &make_cuda_async},
#endif
                                           mr_factory{"Managed", &make_managed},
                                           mr_factory{"Pool", &make_pool},
                                           mr_factory{"Arena", &make_arena},
                                           mr_factory{"Binning", &make_binning},
                                           mr_factory{"Fixed_Size", &make_fixed_size}),
                         [](auto const& info) { return info.param.name; });

// Leave out fixed-size MR here because it can't handle the dynamic allocation sizes
INSTANTIATE_TEST_SUITE_P(ResourceAllocationTests,
                         mr_ref_allocation_test,
                         ::testing::Values(mr_factory{"CUDA", &make_cuda},
#ifdef RMM_CUDA_MALLOC_ASYNC_SUPPORT
                                           mr_factory{"CUDA_Async", &make_cuda_async},
#endif
                                           mr_factory{"Managed", &make_managed},
                                           mr_factory{"Pool", &make_pool},
                                           mr_factory{"Arena", &make_arena},
                                           mr_factory{"Binning", &make_binning}),
                         [](auto const& info) { return info.param.name; });
TEST_P(mr_ref_test, SelfEquality) { EXPECT_TRUE(this->ref == this->ref); }

// Simple reproducer for https://github.com/rapidsai/rmm/issues/861
TEST_P(mr_ref_test, AllocationsAreDifferent) { concurrent_allocations_are_different(this->ref); }

TEST_P(mr_ref_test, AsyncAllocationsAreDifferentDefaultStream)
{
  concurrent_async_allocations_are_different(this->ref, cuda_stream_view{});
}

TEST_P(mr_ref_test, AsyncAllocationsAreDifferent)
{
  concurrent_async_allocations_are_different(this->ref, this->stream);
}

TEST_P(mr_ref_allocation_test, AllocateDefault) { test_various_allocations(this->ref); }

TEST_P(mr_ref_allocation_test, AllocateDefaultStream)
{
  test_various_async_allocations(this->ref, cuda_stream_view{});
}

TEST_P(mr_ref_allocation_test, AllocateOnStream)
{
  test_various_async_allocations(this->ref, this->stream);
}

TEST_P(mr_ref_allocation_test, RandomAllocations) { test_random_allocations(this->ref); }

TEST_P(mr_ref_allocation_test, RandomAllocationsDefaultStream)
{
  test_random_async_allocations(
    this->ref, default_num_allocations, default_max_size, cuda_stream_view{});
}

TEST_P(mr_ref_allocation_test, RandomAllocationsStream)
{
  test_random_async_allocations(this->ref, default_num_allocations, default_max_size, this->stream);
}

TEST_P(mr_ref_allocation_test, MixedRandomAllocationFree)
{
  test_mixed_random_allocation_free(this->ref, default_max_size);
}

TEST_P(mr_ref_allocation_test, MixedRandomAllocationFreeDefaultStream)
{
  test_mixed_random_async_allocation_free(this->ref, default_max_size, cuda_stream_view{});
}

TEST_P(mr_ref_allocation_test, MixedRandomAllocationFreeStream)
{
  test_mixed_random_async_allocation_free(this->ref, default_max_size, this->stream);
}

}  // namespace
}  // namespace rmm::test
