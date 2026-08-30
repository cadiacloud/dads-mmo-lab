#include <StormLib.h>

#include <cstdio>

int main(int argc, char** argv)
{
    if (argc != 3 && argc != 4)
    {
        std::fprintf(
            stderr,
            "usage: %s OUTPUT.MPQ ITEM.DBC [SCALING_STAT_DISTRIBUTION.DBC]\n",
            argv[0]);
        return 2;
    }

    HANDLE archive = nullptr;
    if (!SFileCreateArchive(argv[1], MPQ_CREATE_ARCHIVE_V1 | MPQ_CREATE_LISTFILE, 16, &archive))
    {
        std::fprintf(stderr, "failed to create %s (StormLib error %u)\n", argv[1], SErrGetLastError());
        return 1;
    }

    auto addFile = [archive](char const* localName, char const* archivedName)
    {
        if (SFileAddFileEx(
                archive,
                localName,
                archivedName,
                MPQ_FILE_COMPRESS | MPQ_FILE_REPLACEEXISTING,
                MPQ_COMPRESSION_ZLIB,
                MPQ_COMPRESSION_NEXT_SAME))
        {
            return true;
        }

        std::fprintf(
            stderr,
            "failed to add %s (StormLib error %u)\n",
            archivedName,
            SErrGetLastError());
        return false;
    };

    constexpr char itemArchivedName[] = "DBFilesClient\\Item.dbc";
    constexpr char scalingArchivedName[] = "DBFilesClient\\ScalingStatDistribution.dbc";
    if (!addFile(argv[2], itemArchivedName) ||
        (argc == 4 && !addFile(argv[3], scalingArchivedName)))
    {
        SFileCloseArchive(archive);
        return 1;
    }

    if (!SFileCloseArchive(archive))
    {
        std::fprintf(stderr, "failed to finalize %s (StormLib error %u)\n", argv[1], SErrGetLastError());
        return 1;
    }

    HANDLE verificationArchive = nullptr;
    if (!SFileOpenArchive(argv[1], 0, MPQ_OPEN_READ_ONLY, &verificationArchive))
    {
        std::fprintf(stderr, "could not verify %s (StormLib error %u)\n", argv[1], SErrGetLastError());
        return 1;
    }

    auto verifyFile = [verificationArchive, argv](char const* archivedName)
    {
        HANDLE verificationFile = nullptr;
        if (!SFileOpenFileEx(
                verificationArchive,
                archivedName,
                SFILE_OPEN_FROM_MPQ,
                &verificationFile))
        {
            std::fprintf(
                stderr,
                "could not verify %s in %s (StormLib error %u)\n",
                archivedName,
                argv[1],
                SErrGetLastError());
            return false;
        }

        DWORD highSize = 0;
        DWORD lowSize = SFileGetFileSize(verificationFile, &highSize);
        SFileCloseFile(verificationFile);
        if (lowSize == SFILE_INVALID_SIZE || highSize != 0)
        {
            std::fprintf(stderr, "unexpected archived size for %s\n", archivedName);
            return false;
        }

        std::printf("Verified %s (%u bytes).\n", archivedName, lowSize);
        return true;
    };

    bool const verified = verifyFile(itemArchivedName) &&
        (argc != 4 || verifyFile(scalingArchivedName));
    SFileCloseArchive(verificationArchive);
    if (!verified)
        return 1;

    std::printf("Wrote %s.\n", argv[1]);
    return 0;
}
