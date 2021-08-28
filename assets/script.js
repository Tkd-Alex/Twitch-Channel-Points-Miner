// https://apexcharts.com/javascript-chart-demos/line-charts/zoomable-timeseries/
var options = {
    series: [],
    chart: {
        type: 'area',
        stacked: false,
        height: 490,
        zoom: {
            type: 'x',
            enabled: true,
            autoScaleYaxis: true
        },
        // background: '#2B2D3E',
        foreColor: '#fff'
    },
    dataLabels: {
        enabled: false
    },
    stroke: {
        curve: 'smooth',
    },
    markers: {
        size: 0,
    },
    title: {
        text: 'Channel points (dates are displayed in UTC)',
        align: 'left'
    },
    colors: ["#f9826c"],
    fill: {
        type: 'gradient',
        gradient: {
            shadeIntensity: 1,
            inverseColors: false,
            opacityFrom: 0.5,
            opacityTo: 0,
            stops: [0, 90, 100]
        },
    },
    yaxis: {
        title: {
            text: 'Channel points'
        },
    },
    xaxis: {
        type: 'datetime',
        labels: {
            datetimeUTC: false
        }
    },
    tooltip: {
        theme: 'dark',
        shared: false,
        x: {
            show: true,
            format: 'HH:mm:ss dd MMM',
        },
        custom: ({
            series,
            seriesIndex,
            dataPointIndex,
            w
        }) => {
            return (`<div class="apexcharts-active">
                <div class="apexcharts-tooltip-title">${w.globals.seriesNames[seriesIndex]}</div>
                <div class="apexcharts-tooltip-series-group apexcharts-active" style="order: 1; display: flex; padding-bottom: 0px !important;">
                    <div class="apexcharts-tooltip-text">
                        <div class="apexcharts-tooltip-y-group">
                            <span class="apexcharts-tooltip-text-label"><b>Points</b>: ${series[seriesIndex][dataPointIndex]}</span><br>
                            <span class="apexcharts-tooltip-text-label"><b>Reason</b>: ${w.globals.seriesZ[seriesIndex][dataPointIndex] ? w.globals.seriesZ[seriesIndex][dataPointIndex] : ''}</span>
                        </div>
                    </div>
                </div>
                </div>`)
        }
    },
    noData: {
        text: 'Loading...'
    }
};

var chart = new ApexCharts(document.querySelector("#chart"), options);
var currentStreamer = null;
var annotations = [];

var streamersList = [];
var sortBy = "Name ascending";

var startDate = new Date();
startDate.setDate(startDate.getDate() - daysAgo);
var endDate = new Date();

$(document).ready(function () {
    chart.render();

    if (!localStorage.getItem("annotations")) localStorage.setItem("annotations", true);
    if (!localStorage.getItem("dark-mode")) localStorage.setItem("dark-mode", true);
    if (!localStorage.getItem("sort-by")) localStorage.setItem("sort-by", "Name ascending");

    $('#annotations').prop("checked", localStorage.getItem("annotations") === "true");
    $('#dark-mode').prop("checked", localStorage.getItem("dark-mode") === "true");

    $('#startDate').val(formatDate(startDate));
    $('#endDate').val(formatDate(endDate));

    sortBy = localStorage.getItem("sort-by");
    $('#sorting-by').text(sortBy);
    getStreamers();

    updateAnnotations();
    toggleDarkMode();
});

function formatDate(date) {
    var d = new Date(date),
        month = '' + (d.getMonth() + 1),
        day = '' + d.getDate(),
        year = d.getFullYear();

    if (month.length < 2) month = '0' + month;
    if (day.length < 2) day = '0' + day;

    return [year, month, day].join('-');
}

function changeStreamer(streamer, index) {
    $("li").removeClass("is-active")
    $("li").eq(index - 1).addClass('is-active');
    currentStreamer = streamer;
    getStreamerData(streamer);
}

function getStreamerData(streamer) {
    if (currentStreamer == streamer) {
        $.getJSON(`./json/${streamer}`, {
            startDate: formatDate(startDate),
            endDate: formatDate(endDate)
        }, function (response) {
            chart.updateSeries([{
                name: streamer.replace(".json", ""),
                data: response["series"]
            }], true)
            clearAnnotations();
            annotations = response["annotations"];
            updateAnnotations();
            setTimeout(function () {
                getStreamerData(streamer);
            }, 300000); // 5 minutes
        });
    }
}

function getAllStreamersData() {
    $.getJSON(`./json_all`, function (response) {
        for (var i in response) {
            chart.appendSeries({
                name: response[i]["name"].replace(".json", ""),
                data: response[i]["data"]["series"]
            }, true)
        }
    });
}

function getStreamers() {
    $.getJSON('streamers', function (response) {
        streamersList = response;
        sortStreamers();
        renderStreamers();
    });
}

function renderStreamers() {
    $("#streamers-list").empty();
    var promised = new Promise((resolve, reject) => {
        streamersList.forEach((streamer, index, array) => {
            $("#streamers-list").append(`<li><a onClick="changeStreamer('${streamer.name}', ${index + 1}); return false;">${streamer.name.replace(".json", "")}</a></li>`);
            if (index === array.length - 1) resolve();
        });
    });
    promised.then(() => {
        changeStreamer(streamersList[0].name, 1);
    });
}

function sortStreamers() {
    streamersList = streamersList.sort((a, b) => {
        return (a[sortBy.includes("Name") ? 'name' : 'points'] > b[sortBy.includes("Name") ? 'name' : 'points'] ? 1 : -1) * (sortBy.includes("ascending") ? 1 : -1);
    });
}

function changeSortBy(option) {
    sortBy = option.innerText.trim();
    sortStreamers();
    renderStreamers();
    $('#sorting-by').text(sortBy);
    localStorage.setItem("sort-by", sortBy);
}

function updateAnnotations() {
    if ($('#annotations').prop("checked") === true) {
        clearAnnotations()
        if (annotations && annotations.length > 0)
            annotations.forEach((annotation, index) => {
                annotations[index]['id'] = `id-${index}`
                chart.addXaxisAnnotation(annotation, true)
            })
    } else clearAnnotations()
}

function clearAnnotations() {
    if (annotations && annotations.length > 0)
        annotations.forEach((annotation, index) => {
            chart.removeAnnotation(annotation['id'])
        })
    chart.clearAnnotations();
}

// Toggle
$('#annotations').click(() => {
    updateAnnotations();
});
$('#dark-mode').click(() => {
    toggleDarkMode();
});

$('.dropdown').click(() => {
    $('.dropdown').toggleClass('is-active');
});

// Input date
$('#startDate').change(() => {
    startDate = new Date($('#startDate').val());
    getStreamerData(currentStreamer);
});
$('#endDate').change(() => {
    endDate = new Date($('#endDate').val());
    getStreamerData(currentStreamer);
});
