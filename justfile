# china-abs — root task runner (just)
#
# Run from the repository root:  just <recipe>

set shell := ["bash", "-cu"]

dir := justfile_directory()
today := `date +%Y%m%d`

# Show available recipes
default:
    @just --list

# Build the image locally, then stream it to xiaoyu@tencent-01 and load it
# there.  The build tag and the uploaded tag are the same; it defaults to
# today's date (YYYYMMDD), e.g. china-abs:20260920.
# e.g. `just upload-docker-tencent` or `just upload-docker-tencent china-abs:dev`
upload-docker-tencent image=("china-abs:" + today):
    docker build -t {{image}} {{dir}}
    docker save {{image}} | gzip | ssh xiaoyu@tencent-01 "gunzip | docker load"
