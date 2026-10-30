"""Legacy pipeline units inject this alongside their non-MP4 renderer stubs.

Actual MP4 inspection is exercised by test_final_output_pixels/media and the
dedicated final-output pipeline/service tests; this is never an autouse bypass.
"""


def passing_final_inspection(**kwargs):
    return list(kwargs["exports"])
