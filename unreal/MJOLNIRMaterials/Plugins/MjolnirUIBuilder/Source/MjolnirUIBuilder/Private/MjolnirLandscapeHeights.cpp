#include "MjolnirUIBuilderLibrary.h"
#include "Landscape.h"
#include "LandscapeInfo.h"
#include "LandscapeEdit.h"
#include "Misc/FileHelper.h"

bool UMjolnirUIBuilderLibrary::PatchLandscapeHeights(ALandscape* Landscape, const FString& BaselineR16,
    const FString& CandidateR16, bool bVerifyOnly)
{
    if (!Landscape || Landscape->HasLayersContent())
    {
        return false;
    }
    ULandscapeInfo* Info = Landscape->GetLandscapeInfo();
    int32 X0, Y0, X1, Y1;
    if (!Info || !Info->GetLandscapeExtent(X0, Y0, X1, Y1))
    {
        return false;
    }
    const int32 Width = X1 - X0 + 1;
    const int32 Height = Y1 - Y0 + 1;
    const int64 ByteCount = int64(Width) * Height * sizeof(uint16);
    TArray<uint8> BaselineBytes, CandidateBytes;
    if (!FFileHelper::LoadFileToArray(BaselineBytes, *BaselineR16) ||
        !FFileHelper::LoadFileToArray(CandidateBytes, *CandidateR16) ||
        BaselineBytes.Num() != ByteCount || CandidateBytes.Num() != ByteCount)
    {
        return false;
    }
    const uint16* Baseline = reinterpret_cast<const uint16*>(BaselineBytes.GetData());
    const uint16* Candidate = reinterpret_cast<const uint16*>(CandidateBytes.GetData());
    TArray<uint16> Actual;
    Actual.SetNumZeroed(Width * Height);
    {
        FLandscapeEditDataInterface Read(Info);
        Read.GetHeightDataFast(X0, Y0, X1, Y1, Actual.GetData(), Width);
    }
    if (FMemory::Memcmp(Actual.GetData(), bVerifyOnly ? Candidate : Baseline, ByteCount) != 0)
    {
        return false;
    }
    if (bVerifyOnly)
    {
        return true;
    }

    FIntRect Region(Width, Height, 0, 0);
    for (int32 Index = 0; Index < Actual.Num(); ++Index)
    {
        if (Baseline[Index] != Candidate[Index])
        {
            Region.Include(FIntPoint(Index % Width, Index / Width));
        }
    }
    if (Region.Min.X > Region.Max.X)
    {
        return true;
    }

    // Include an unchanged ring so the incident boundary normals are regenerated.
    Region.Min.X = FMath::Max(0, Region.Min.X - 1);
    Region.Min.Y = FMath::Max(0, Region.Min.Y - 1);
    Region.Max.X = FMath::Min(Width - 1, Region.Max.X + 1);
    Region.Max.Y = FMath::Min(Height - 1, Region.Max.Y + 1);
    TArray<uint16> Patch;
    Patch.Reserve((Region.Width() + 1) * (Region.Height() + 1));
    for (int32 Row = Region.Min.Y; Row <= Region.Max.Y; ++Row)
    {
        Patch.Append(Candidate + Row * Width + Region.Min.X, Region.Width() + 1);
    }
    Landscape->Modify();
    {
        FHeightmapAccessor<false> Edit(Info);
        Edit.SetData(X0 + Region.Min.X, Y0 + Region.Min.Y, X0 + Region.Max.X, Y0 + Region.Max.Y, Patch.GetData());
    }
    Landscape->MarkPackageDirty();
    return true;
}
