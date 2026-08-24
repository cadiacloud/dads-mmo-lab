#include <StormLib.h>

#include <cstdio>

int main(int argc, char** argv)
{
    if (argc != 3)
    {
        std::fprintf(stderr, "usage: %s OUTPUT.MPQ ITEM.DBC\n", argv[0]);
        return 2;
    }

    HANDLE archive = nullptr;
    if (!SFileCreateArchive(argv[1], MPQ_CREATE_ARCHIVE_V1 | MPQ_CREATE_LISTFILE, 8, &archive))
    {
        std::fprintf(stderr, "failed to create %s (StormLib error %u)\n", argv[1], SErrGetLastError());
        return 1;
    }

    constexpr char archivedName[] = "DBFilesClient\\Item.dbc";
    bool added = SFileAddFileEx(
        archive,
        argv[2],
        archivedName,
        MPQ_FILE_COMPRESS | MPQ_FILE_REPLACEEXISTING,
        MPQ_COMPRESSION_ZLIB,
        MPQ_COMPRESSION_NEXT_SAME);
    if (!added)
    {
        std::fprintf(stderr, "failed to add %s (StormLib error %u)\n", archivedName, SErrGetLastError());
        SFileCloseArchive(archive);
        return 1;
    }

    if (!SFileCloseArchive(archive))
    {
        std::fprintf(stderr, "failed to finalize %s (StormLib error %u)\n", argv[1], SErrGetLastError());
        return 1;
    }

    HANDLE verificationArchive = nullptr;
    HANDLE verificationFile = nullptr;
    if (!SFileOpenArchive(argv[1], 0, MPQ_OPEN_READ_ONLY, &verificationArchive)
        || !SFileOpenFileEx(verificationArchive, archivedName, SFILE_OPEN_FROM_MPQ, &verificationFile))
    {
        std::fprintf(stderr, "could not verify %s in %s (StormLib error %u)\n",
            archivedName, argv[1], SErrGetLastError());
        if (verificationArchive)
            SFileCloseArchive(verificationArchive);
        return 1;
    }

    DWORD highSize = 0;
    DWORD lowSize = SFileGetFileSize(verificationFile, &highSize);
    SFileCloseFile(verificationFile);
    SFileCloseArchive(verificationArchive);
    if (lowSize == SFILE_INVALID_SIZE || highSize != 0)
    {
        std::fprintf(stderr, "unexpected archived Item.dbc size\n");
        return 1;
    }

    std::printf("Wrote %s with %s (%u bytes verified).\n", argv[1], archivedName, lowSize);
    return 0;
}
